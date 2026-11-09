from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Iterator, Literal, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


MEMORY_CATEGORIES = frozenset({"semantic", "preference", "routine"})
MAX_MEMORY_CONTENT_LENGTH = 300
SENSITIVE_MEMORY_PATTERN = re.compile(
    r"(?:password|passcode|token|api[\s_-]*key|secret|"
    r"密码|口令|令牌|密钥|身份证|银行卡|信用卡)",
    re.IGNORECASE,
)
CARD_NUMBER_PATTERN = re.compile(r"(?:\d[ -]?){13,19}")


def _normalize_content(value: str) -> str:
    return " ".join(value.strip().split())


def is_memory_content_allowed(content: str) -> bool:
    normalized = _normalize_content(content)
    return bool(normalized) and not (
        SENSITIVE_MEMORY_PATTERN.search(normalized)
        or CARD_NUMBER_PATTERN.search(normalized)
    )


class MemoryDraft(BaseModel):
    """User-editable memory content. Saving always requires a later confirmation."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_MEMORY_CONTENT_LENGTH)
    category: Literal["semantic", "preference", "routine"] = "semantic"

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = _normalize_content(value)
        if not normalized:
            raise ValueError("记忆内容不能为空")
        if not is_memory_content_allowed(normalized):
            raise ValueError("候选记忆疑似包含敏感凭据或卡号，不能保存")
        return normalized


class MemorySuggestion(MemoryDraft):
    """A model proposal that is not persisted as a confirmed memory."""


class MemoryCandidate(MemoryDraft):
    id: str
    session_id: str
    source: str = "conversation"
    created_at: str
    updated_at: str


class MemoryRecord(MemoryDraft):
    id: str
    source_session_id: str
    source: str = "user_confirmed_conversation"
    confidence: float = Field(ge=0, le=1)
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MemoryStore:
    """Small local SQLite store for explicitly confirmed, editable memories."""

    database_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", Lock())
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def list_candidates(self, limit: int = 100) -> list[MemoryCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, content, category, source, created_at, updated_at
                FROM memory_candidates
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def list_memories(self, limit: int = 100) -> list[MemoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_session_id, content, category, source, confidence, created_at, updated_at
                FROM memories
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def context(self, limit: int) -> tuple[MemoryRecord, ...]:
        return tuple(self.list_memories(limit))

    def create_candidates(
        self,
        session_id: str,
        suggestions: Sequence[MemorySuggestion | MemoryCandidate],
    ) -> list[MemoryCandidate]:
        now = self._timestamp()
        created: list[MemoryCandidate] = []
        with self._locked_connection() as connection:
            for suggestion in suggestions[:3]:
                content_key = suggestion.content.casefold()
                existing = connection.execute(
                    """
                    SELECT id, session_id, content, category, source, created_at, updated_at
                    FROM memory_candidates
                    WHERE content_key = ?
                    """,
                    (content_key,),
                ).fetchone()
                if existing is not None:
                    created.append(self._candidate_from_row(existing))
                    continue
                confirmed = connection.execute(
                    "SELECT 1 FROM memories WHERE content_key = ?",
                    (content_key,),
                ).fetchone()
                if confirmed is not None:
                    continue

                candidate = MemoryCandidate(
                    id=f"memc_{uuid4().hex}",
                    session_id=session_id,
                    content=suggestion.content,
                    category=suggestion.category,
                    created_at=now,
                    updated_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO memory_candidates (
                        id, session_id, content, content_key, category, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.id,
                        candidate.session_id,
                        candidate.content,
                        content_key,
                        candidate.category,
                        candidate.source,
                        candidate.created_at,
                        candidate.updated_at,
                    ),
                )
                created.append(candidate)
        return created

    def update_candidate(self, candidate_id: str, draft: MemoryDraft) -> MemoryCandidate | None:
        now = self._timestamp()
        with self._locked_connection() as connection:
            result = connection.execute(
                """
                UPDATE memory_candidates
                SET content = ?, content_key = ?, category = ?, updated_at = ?
                WHERE id = ?
                """,
                (draft.content, draft.content.casefold(), draft.category, now, candidate_id),
            )
            if result.rowcount != 1:
                return None
            row = connection.execute(
                """
                SELECT id, session_id, content, category, source, created_at, updated_at
                FROM memory_candidates WHERE id = ?
                """,
                (candidate_id,),
            ).fetchone()
        return self._candidate_from_row(row)

    def confirm_candidate(self, candidate_id: str, draft: MemoryDraft) -> MemoryRecord | None:
        now = self._timestamp()
        with self._locked_connection() as connection:
            candidate = connection.execute(
                """
                SELECT id, session_id, source FROM memory_candidates WHERE id = ?
                """,
                (candidate_id,),
            ).fetchone()
            if candidate is None:
                return None

            existing = connection.execute(
                """
                SELECT id, source_session_id, content, category, source, confidence, created_at, updated_at
                FROM memories WHERE content_key = ?
                """,
                (draft.content.casefold(),),
            ).fetchone()
            if existing is not None:
                connection.execute("DELETE FROM memory_candidates WHERE id = ?", (candidate_id,))
                return self._record_from_row(existing)

            memory = MemoryRecord(
                id=f"mem_{uuid4().hex}",
                source_session_id=str(candidate["session_id"]),
                content=draft.content,
                category=draft.category,
                confidence=1.0,
                created_at=now,
                updated_at=now,
            )
            connection.execute(
                """
                INSERT INTO memories (
                    id, source_session_id, content, content_key, category, source, confidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    memory.source_session_id,
                    memory.content,
                    memory.content.casefold(),
                    memory.category,
                    memory.source,
                    memory.confidence,
                    memory.created_at,
                    memory.updated_at,
                ),
            )
            connection.execute("DELETE FROM memory_candidates WHERE id = ?", (candidate_id,))
        return memory

    def delete_candidate(self, candidate_id: str) -> bool:
        with self._locked_connection() as connection:
            return connection.execute(
                "DELETE FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).rowcount == 1

    def update_memory(self, memory_id: str, draft: MemoryDraft) -> MemoryRecord | None:
        now = self._timestamp()
        with self._locked_connection() as connection:
            result = connection.execute(
                """
                UPDATE memories
                SET content = ?, content_key = ?, category = ?, updated_at = ?
                WHERE id = ?
                """,
                (draft.content, draft.content.casefold(), draft.category, now, memory_id),
            )
            if result.rowcount != 1:
                return None
            row = connection.execute(
                """
                SELECT id, source_session_id, content, category, source, confidence, created_at, updated_at
                FROM memories WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
        return self._record_from_row(row)

    def delete_memory(self, memory_id: str) -> bool:
        with self._locked_connection() as connection:
            return connection.execute(
                "DELETE FROM memories WHERE id = ?",
                (memory_id,),
            ).rowcount == 1

    def _initialize(self) -> None:
        with self._locked_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_candidates_updated_at
                    ON memory_candidates (updated_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_candidates_content_key
                    ON memory_candidates (content_key);

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    source_session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_key TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_updated_at
                    ON memories (updated_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _locked_connection(self) -> Iterator[sqlite3.Connection]:
        lock = getattr(self, "_lock")
        with lock, self._connect() as connection:
            yield connection

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _candidate_from_row(row: sqlite3.Row) -> MemoryCandidate:
        return MemoryCandidate(
            id=row["id"],
            session_id=row["session_id"],
            content=row["content"],
            category=row["category"],
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            source_session_id=row["source_session_id"],
            content=row["content"],
            category=row["category"],
            source=row["source"],
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
