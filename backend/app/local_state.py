from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Awaitable, Callable, Iterator, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .pet_events import PetActionEvent


ReminderStatus = Literal["pending", "fired", "cancelled"]
LogStatus = Literal["success", "info", "warning", "failure"]
LANGUAGES = frozenset({"zh-CN", "ja-JP", "en-US"})


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_timestamp(value: str, *, require_future: bool) -> str:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("提醒时间必须是带时区的 ISO 8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("提醒时间必须包含时区")
    normalized = parsed.astimezone(UTC)
    if require_future and normalized <= datetime.now(UTC):
        raise ValueError("提醒时间必须晚于当前时间")
    return normalized.isoformat()


class ReminderCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str = Field(min_length=1, max_length=180)
    remind_at: str = Field(alias="remindAt", min_length=1, max_length=64)
    session_id: str = Field(default="reminder-session", alias="sessionId", min_length=1, max_length=128)

    @field_validator("title", "session_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = _normalize_text(value)
        if not value:
            raise ValueError("内容不能为空")
        return value

    @field_validator("remind_at")
    @classmethod
    def validate_remind_at(cls, value: str) -> str:
        return _normalize_timestamp(value, require_future=True)


class ReminderUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=180)
    remind_at: str | None = Field(default=None, alias="remindAt", min_length=1, max_length=64)

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _normalize_text(value)
        if not value:
            raise ValueError("提醒内容不能为空")
        return value

    @field_validator("remind_at")
    @classmethod
    def validate_optional_remind_at(cls, value: str | None) -> str | None:
        return _normalize_timestamp(value, require_future=True) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "ReminderUpdateRequest":
        if self.title is None and self.remind_at is None:
            raise ValueError("至少需要修改一个提醒字段")
        return self


class ReminderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    title: str
    remind_at: str
    status: ReminderStatus
    created_at: str
    updated_at: str
    fired_at: str | None = None


class ReminderDeleteResponse(BaseModel):
    deleted: bool


class DesktopSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["zh-CN", "ja-JP", "en-US"] = "zh-CN"
    personality: Literal["warm", "balanced", "concise"] = "warm"
    voice_preference: Literal["default", "gentle", "lively"] = "default"
    memory_policy: Literal["ask_before_save", "disabled"] = "ask_before_save"
    permission_mode: Literal["owner_confirmation"] = "owner_confirmation"
    diagnostics_enabled: bool = True
    updated_at: str


class DesktopSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["zh-CN", "ja-JP", "en-US"] | None = None
    personality: Literal["warm", "balanced", "concise"] | None = None
    voice_preference: Literal["default", "gentle", "lively"] | None = None
    memory_policy: Literal["ask_before_save", "disabled"] | None = None
    diagnostics_enabled: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "DesktopSettingsUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("至少需要修改一个设置项")
        return self


class SystemLogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Literal["reminder", "settings", "identity", "system"]
    event_type: str
    status: LogStatus
    message: str
    created_at: str


@dataclass(frozen=True)
class LocalStateStore:
    """Local-only state for reminders, user preferences, and safe event logs."""

    database_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", Lock())
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_reminder(self, request: ReminderCreateRequest) -> ReminderRecord:
        now = _timestamp()
        reminder = ReminderRecord(
            id=f"rem_{uuid4().hex}",
            session_id=request.session_id,
            title=request.title,
            remind_at=request.remind_at,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        with self._locked_connection() as connection:
            connection.execute(
                """
                INSERT INTO reminders (
                    id, session_id, title, remind_at, status, created_at, updated_at, fired_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reminder.id,
                    reminder.session_id,
                    reminder.title,
                    reminder.remind_at,
                    reminder.status,
                    reminder.created_at,
                    reminder.updated_at,
                    reminder.fired_at,
                ),
            )
            self._insert_log(
                connection,
                category="reminder",
                event_type="reminder.created",
                status="success",
                message="提醒已创建",
            )
        return reminder

    def list_reminders(self, status: ReminderStatus | None = None, limit: int = 100) -> list[ReminderRecord]:
        limit = max(1, min(limit, 100))
        clauses = ""
        parameters: tuple[object, ...] = (limit,)
        if status is not None:
            clauses = "WHERE status = ?"
            parameters = (status, limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, session_id, title, remind_at, status, created_at, updated_at, fired_at
                FROM reminders
                {clauses}
                ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'fired' THEN 1 ELSE 2 END,
                         remind_at ASC,
                         updated_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._reminder_from_row(row) for row in rows]

    def update_reminder(self, reminder_id: str, request: ReminderUpdateRequest) -> ReminderRecord | None:
        with self._locked_connection() as connection:
            existing = connection.execute(
                """
                SELECT id, session_id, title, remind_at, status, created_at, updated_at, fired_at
                FROM reminders WHERE id = ?
                """,
                (reminder_id,),
            ).fetchone()
            if existing is None or existing["status"] != "pending":
                return None
            reminder = self._reminder_from_row(existing)
            now = _timestamp()
            updated = reminder.model_copy(update={
                "title": request.title if request.title is not None else reminder.title,
                "remind_at": request.remind_at if request.remind_at is not None else reminder.remind_at,
                "updated_at": now,
            })
            connection.execute(
                "UPDATE reminders SET title = ?, remind_at = ?, updated_at = ? WHERE id = ?",
                (updated.title, updated.remind_at, updated.updated_at, reminder_id),
            )
            self._insert_log(
                connection,
                category="reminder",
                event_type="reminder.updated",
                status="success",
                message="提醒已更新",
            )
        return updated

    def cancel_reminder(self, reminder_id: str) -> bool:
        now = _timestamp()
        with self._locked_connection() as connection:
            result = connection.execute(
                """
                UPDATE reminders
                SET status = 'cancelled', updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, reminder_id),
            )
            if result.rowcount != 1:
                return False
            self._insert_log(
                connection,
                category="reminder",
                event_type="reminder.cancelled",
                status="info",
                message="提醒已取消",
            )
        return True

    def claim_due_reminders(self, now: datetime | None = None) -> list[ReminderRecord]:
        due_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        fired_at = _timestamp()
        with self._locked_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, title, remind_at, status, created_at, updated_at, fired_at
                FROM reminders
                WHERE status = 'pending' AND remind_at <= ?
                ORDER BY remind_at ASC
                """,
                (due_at,),
            ).fetchall()
            claimed: list[ReminderRecord] = []
            for row in rows:
                result = connection.execute(
                    """
                    UPDATE reminders
                    SET status = 'fired', fired_at = ?, updated_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (fired_at, fired_at, row["id"]),
                )
                if result.rowcount != 1:
                    continue
                claimed.append(self._reminder_from_row(row).model_copy(update={
                    "status": "fired",
                    "fired_at": fired_at,
                    "updated_at": fired_at,
                }))
        return claimed

    def record_reminder_delivery(self, *, delivered: int, failed: bool = False) -> None:
        with self._locked_connection() as connection:
            self._insert_log(
                connection,
                category="reminder",
                event_type="reminder.fired",
                status="failure" if failed else ("success" if delivered else "info"),
                message="提醒动作派发失败" if failed else ("提醒动作已派发" if delivered else "提醒已到期，等待桌宠连接"),
            )

    def get_settings(self) -> DesktopSettings:
        with self._locked_connection() as connection:
            row = connection.execute(
                """
                SELECT language, personality, voice_preference, memory_policy, permission_mode,
                       diagnostics_enabled, updated_at
                FROM desktop_settings WHERE id = 1
                """
            ).fetchone()
            if row is None:
                now = _timestamp()
                connection.execute(
                    """
                    INSERT INTO desktop_settings (
                        id, language, personality, voice_preference, memory_policy,
                        permission_mode, diagnostics_enabled, updated_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("zh-CN", "warm", "default", "ask_before_save", "owner_confirmation", 1, now),
                )
                return DesktopSettings(updated_at=now)
        return self._settings_from_row(row)

    def update_settings(self, update: DesktopSettingsUpdate) -> DesktopSettings:
        current = self.get_settings()
        values = current.model_dump()
        values.update(update.model_dump(exclude_none=True))
        values["permission_mode"] = "owner_confirmation"
        values["updated_at"] = _timestamp()
        settings = DesktopSettings(**values)
        with self._locked_connection() as connection:
            connection.execute(
                """
                UPDATE desktop_settings
                SET language = ?, personality = ?, voice_preference = ?, memory_policy = ?,
                    permission_mode = ?, diagnostics_enabled = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    settings.language,
                    settings.personality,
                    settings.voice_preference,
                    settings.memory_policy,
                    settings.permission_mode,
                    int(settings.diagnostics_enabled),
                    settings.updated_at,
                ),
            )
            self._insert_log(
                connection,
                category="settings",
                event_type="settings.updated",
                status="success",
                message="本地偏好已更新",
            )
        return settings

    def list_logs(self, limit: int = 100) -> list[SystemLogRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, category, event_type, status, message, created_at
                FROM system_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [SystemLogRecord(**dict(row)) for row in rows]

    def record_system_event(
        self,
        *,
        event_type: str,
        status: LogStatus,
        message: str,
        category: Literal["identity", "system"] = "system",
    ) -> None:
        """写入不包含凭据、原始音频或完整声纹标识的安全摘要日志。"""
        with self._locked_connection() as connection:
            self._insert_log(
                connection,
                category=category,
                event_type=event_type,
                status=status,
                message=message,
            )

    def _initialize(self) -> None:
        with self._locked_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    fired_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_due
                    ON reminders (status, remind_at);

                CREATE TABLE IF NOT EXISTS desktop_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    language TEXT NOT NULL,
                    personality TEXT NOT NULL,
                    voice_preference TEXT NOT NULL,
                    memory_policy TEXT NOT NULL,
                    permission_mode TEXT NOT NULL,
                    diagnostics_enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS system_logs (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_system_logs_created_at
                    ON system_logs (created_at DESC);
                """
            )

    def _insert_log(
        self,
        connection: sqlite3.Connection,
        *,
        category: Literal["reminder", "settings", "identity", "system"],
        event_type: str,
        status: LogStatus,
        message: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO system_logs (id, category, event_type, status, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"log_{uuid4().hex}", category, event_type, status, message, _timestamp()),
        )

    @contextmanager
    def _locked_connection(self) -> Iterator[sqlite3.Connection]:
        lock = getattr(self, "_lock")
        with lock, self._connect() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _reminder_from_row(row: sqlite3.Row) -> ReminderRecord:
        return ReminderRecord(
            id=row["id"],
            session_id=row["session_id"],
            title=row["title"],
            remind_at=row["remind_at"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            fired_at=row["fired_at"],
        )

    @staticmethod
    def _settings_from_row(row: sqlite3.Row) -> DesktopSettings:
        return DesktopSettings(
            language=row["language"],
            personality=row["personality"],
            voice_preference=row["voice_preference"],
            memory_policy=row["memory_policy"],
            permission_mode=row["permission_mode"],
            diagnostics_enabled=bool(row["diagnostics_enabled"]),
            updated_at=row["updated_at"],
        )


class ReminderDispatcher:
    """Polls SQLite so pending reminders survive a local gateway restart."""

    def __init__(
        self,
        store: LocalStateStore,
        broadcast: Callable[[PetActionEvent], Awaitable[int]],
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.store = store
        self.broadcast = broadcast
        self.poll_interval_seconds = max(0.2, poll_interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stopping: asyncio.Event | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        # Each FastAPI lifespan may run on a new event loop (including tests).
        # Keep loop-bound synchronization primitives within that lifespan.
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="desktop-pet-reminders")

    async def stop(self) -> None:
        if self._task is None:
            return
        if self._stopping is not None:
            self._stopping.set()
        await self._task
        self._task = None
        self._stopping = None

    async def dispatch_due(self, now: datetime | None = None) -> int:
        reminders = self.store.claim_due_reminders(now)
        for _reminder in reminders:
            try:
                delivered = await self.broadcast(PetActionEvent(
                    action_id="reminder",
                    emotion="gentle",
                    mouth_mode="closed",
                    duration_ms=8_000,
                    interruptible=True,
                ))
            except Exception:
                self.store.record_reminder_delivery(delivered=0, failed=True)
                continue
            self.store.record_reminder_delivery(delivered=delivered)
        return len(reminders)

    async def _run(self) -> None:
        stopping = self._stopping
        if stopping is None:
            return
        while not stopping.is_set():
            try:
                await self.dispatch_due()
            except Exception:
                # The loop must stay alive; details remain local in the event log.
                self.store.record_reminder_delivery(delivered=0, failed=True)
            try:
                await asyncio.wait_for(stopping.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                pass


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
