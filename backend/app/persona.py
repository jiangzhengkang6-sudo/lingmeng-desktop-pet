from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .pet_events import PET_ACTIONS


PERSONA_NAME_MAX = 60
PERSONA_TEXT_MAX = 2_000
PERSONA_PROMPT_MAX = 4_000
VOICE_ID_MAX = 120


class PersonaError(Exception):
    def __init__(self, message: str, code: str = "PERSONA_ERROR", status_code: int = 500):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class PersonaProfileDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str = Field(min_length=1, max_length=PERSONA_NAME_MAX)
    character_name: str = Field(min_length=1, max_length=PERSONA_NAME_MAX)
    personality: str = Field(min_length=1, max_length=PERSONA_TEXT_MAX)
    speaking_style: str = Field(min_length=1, max_length=PERSONA_TEXT_MAX)
    default_action: str = Field(min_length=1, max_length=32)
    voice_id: str = Field(default="", max_length=VOICE_ID_MAX)
    system_prompt: str = Field(default="", max_length=PERSONA_PROMPT_MAX)

    @field_validator("profile_name", "character_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("personality", "speaking_style", "voice_id")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("system_prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        return value.strip()

    @field_validator("default_action")
    @classmethod
    def validate_default_action(cls, value: str) -> str:
        value = value.strip()
        if value not in PET_ACTIONS:
            raise ValueError("默认动作不受支持")
        return value

    @model_validator(mode="after")
    def require_profile_content(self) -> "PersonaProfileDraft":
        if not self.profile_name.strip() or not self.character_name.strip():
            raise ValueError("配置名称与桌宠名称不能为空")
        return self


class PersonaProfile(PersonaProfileDraft):
    id: str
    is_active: bool
    created_at: str
    updated_at: str


class PersonaProfileVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: str
    profile_id: str
    snapshot: PersonaProfileDraft
    note: str
    created_at: str


@dataclass(frozen=True)
class PersonaStore:
    """本地 SQLite 人格配置库：支持启用、停用与版本回滚。"""

    database_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", Lock())
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def list_profiles(self) -> list[PersonaProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM persona_profiles ORDER BY is_active DESC, updated_at DESC"
            ).fetchall()
        return [self._profile_from_row(row) for row in rows]

    def get_profile(self, profile_id: str) -> PersonaProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM persona_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return self._profile_from_row(row) if row is not None else None

    def get_active(self) -> PersonaProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM persona_profiles WHERE is_active = 1 LIMIT 1"
            ).fetchone()
        return self._profile_from_row(row) if row is not None else None

    def create_profile(self, draft: PersonaProfileDraft) -> PersonaProfile:
        now = self._timestamp()
        profile = PersonaProfile(
            id=f"persona_{uuid4().hex}",
            is_active=False,
            created_at=now,
            updated_at=now,
            **draft.model_dump(),
        )
        with self._locked_connection() as connection:
            connection.execute(
                """
                INSERT INTO persona_profiles (
                    id, profile_name, character_name, personality, speaking_style,
                    default_action, voice_id, system_prompt, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.profile_name,
                    profile.character_name,
                    profile.personality,
                    profile.speaking_style,
                    profile.default_action,
                    profile.voice_id,
                    profile.system_prompt,
                    0,
                    now,
                    now,
                ),
            )
        return profile

    def update_profile(
        self,
        profile_id: str,
        draft: PersonaProfileDraft,
    ) -> PersonaProfile | None:
        with self._locked_connection() as connection:
            existing_row = connection.execute(
                "SELECT * FROM persona_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if existing_row is None:
                return None
            existing = self._profile_from_row(existing_row)
            self._insert_version(connection, existing, note="更新前快照")
            now = self._timestamp()
            connection.execute(
                """
                UPDATE persona_profiles
                SET profile_name = ?, character_name = ?, personality = ?, speaking_style = ?,
                    default_action = ?, voice_id = ?, system_prompt = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    draft.profile_name,
                    draft.character_name,
                    draft.personality,
                    draft.speaking_style,
                    draft.default_action,
                    draft.voice_id,
                    draft.system_prompt,
                    now,
                    profile_id,
                ),
            )
        return self.get_profile(profile_id)

    def activate(self, profile_id: str) -> PersonaProfile | None:
        with self._locked_connection() as connection:
            target = connection.execute(
                "SELECT id FROM persona_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if target is None:
                return None
            connection.execute("UPDATE persona_profiles SET is_active = 0")
            connection.execute(
                "UPDATE persona_profiles SET is_active = 1 WHERE id = ?",
                (profile_id,),
            )
        return self.get_profile(profile_id)

    def deactivate_all(self) -> None:
        with self._locked_connection() as connection:
            connection.execute("UPDATE persona_profiles SET is_active = 0")

    def delete_profile(self, profile_id: str) -> bool:
        with self._locked_connection() as connection:
            connection.execute(
                "DELETE FROM persona_profile_versions WHERE profile_id = ?",
                (profile_id,),
            )
            result = connection.execute(
                "DELETE FROM persona_profiles WHERE id = ?",
                (profile_id,),
            )
        return result.rowcount == 1

    def list_versions(self, profile_id: str) -> list[PersonaProfileVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT version_id, profile_id, snapshot_json, note, created_at
                FROM persona_profile_versions
                WHERE profile_id = ?
                ORDER BY created_at DESC
                """,
                (profile_id,),
            ).fetchall()
        return [self._version_from_row(row) for row in rows]

    def rollback(
        self,
        profile_id: str,
        version_id: str,
    ) -> PersonaProfile | None:
        with self._locked_connection() as connection:
            profile_row = connection.execute(
                "SELECT * FROM persona_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            version_row = connection.execute(
                "SELECT * FROM persona_profile_versions WHERE version_id = ? AND profile_id = ?",
                (version_id, profile_id),
            ).fetchone()
            if profile_row is None or version_row is None:
                return None
            current = self._profile_from_row(profile_row)
            self._insert_version(connection, current, note="回滚前快照")
            snapshot = PersonaProfileDraft.model_validate_json(version_row["snapshot_json"])
            now = self._timestamp()
            connection.execute(
                """
                UPDATE persona_profiles
                SET profile_name = ?, character_name = ?, personality = ?, speaking_style = ?,
                    default_action = ?, voice_id = ?, system_prompt = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    snapshot.profile_name,
                    snapshot.character_name,
                    snapshot.personality,
                    snapshot.speaking_style,
                    snapshot.default_action,
                    snapshot.voice_id,
                    snapshot.system_prompt,
                    now,
                    profile_id,
                ),
            )
        return self.get_profile(profile_id)

    def _insert_version(
        self,
        connection: sqlite3.Connection,
        profile: PersonaProfile,
        *,
        note: str,
    ) -> None:
        snapshot = PersonaProfileDraft(
            profile_name=profile.profile_name,
            character_name=profile.character_name,
            personality=profile.personality,
            speaking_style=profile.speaking_style,
            default_action=profile.default_action,
            voice_id=profile.voice_id,
            system_prompt=profile.system_prompt,
        )
        connection.execute(
            """
            INSERT INTO persona_profile_versions (version_id, profile_id, snapshot_json, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"personav_{uuid4().hex}",
                profile.id,
                snapshot.model_dump_json(),
                note,
                self._timestamp(),
            ),
        )

    def _initialize(self) -> None:
        with self._locked_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS persona_profiles (
                    id TEXT PRIMARY KEY,
                    profile_name TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    personality TEXT NOT NULL,
                    speaking_style TEXT NOT NULL,
                    default_action TEXT NOT NULL,
                    voice_id TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS persona_profile_versions (
                    version_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_persona_versions_profile
                    ON persona_profile_versions (profile_id, created_at DESC);
                """
            )

    @staticmethod
    def _profile_from_row(row: sqlite3.Row) -> PersonaProfile:
        return PersonaProfile(
            id=row["id"],
            profile_name=row["profile_name"],
            character_name=row["character_name"],
            personality=row["personality"],
            speaking_style=row["speaking_style"],
            default_action=row["default_action"],
            voice_id=row["voice_id"],
            system_prompt=row["system_prompt"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _version_from_row(row: sqlite3.Row) -> PersonaProfileVersion:
        return PersonaProfileVersion(
            version_id=row["version_id"],
            profile_id=row["profile_id"],
            snapshot=PersonaProfileDraft.model_validate_json(row["snapshot_json"]),
            note=row["note"],
            created_at=row["created_at"],
        )

    @contextmanager
    def _connect(self) -> object:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _locked_connection(self) -> object:
        lock = getattr(self, "_lock")
        with lock, self._connect() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()


def build_persona_prompt_block(profile: PersonaProfile) -> str:
    """把启用人格转成系统提示词中的人格区块。"""
    lines = [
        f"You are {profile.character_name}, an embodied desktop companion (desktop pet).",
        f"Character name: {profile.character_name}",
        f"Personality: {profile.personality}",
        f"Speaking style: {profile.speaking_style}",
        f"Default action when idle: {profile.default_action}",
    ]
    if profile.voice_id.strip():
        lines.append(f"Preferred voice id: {profile.voice_id.strip()}")
    if profile.system_prompt.strip():
        lines.append(
            "Core persona instruction (follow it while keeping the output protocol):\n"
            + profile.system_prompt.strip()
        )
    return "\n".join(lines)
