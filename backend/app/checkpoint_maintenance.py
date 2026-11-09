from __future__ import annotations

import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import Settings


StateInspector = Callable[[str], Awaitable[Any]]


class CheckpointThreadSummary(BaseModel):
    """单个检查点线程的非内容摘要。"""

    thread_id: str
    checkpoint_count: int
    write_count: int
    latest_checkpoint_id: str
    latest_source: str | None = None
    latest_step: int | None = None
    pending: bool | None = None


class CheckpointDatabaseSummary(BaseModel):
    """检查点数据库维护状态。

    该模型只返回路径、计数和节点步骤，不返回用户消息、记忆或文件参数内容。
    """

    enabled: bool
    path: str
    exists: bool
    size_bytes: int
    thread_count: int
    checkpoint_count: int
    write_count: int
    threads: list[CheckpointThreadSummary]


class CheckpointCleanupRequest(BaseModel):
    """检查点清理请求。

    默认只清理已经结束的图线程；delete_all 必须显式提供确认文本，避免误删
    仍在等待审批或远程模型返回的状态。
    """

    only_completed: bool = True
    delete_all: bool = False
    confirm: Literal["DELETE_ALL"] | None = None
    vacuum: bool = True


class CheckpointCleanupResult(BaseModel):
    """检查点清理结果。"""

    deleted_thread_ids: list[str] = Field(default_factory=list)
    retained_thread_ids: list[str] = Field(default_factory=list)
    checkpoint_count_before: int
    checkpoint_count_after: int
    write_count_before: int
    write_count_after: int
    vacuumed: bool


class CheckpointMaintenanceService:
    """LangGraph SQLite 检查点的本地只读查看与安全清理服务。"""

    def __init__(
        self,
        settings: Settings,
        inspect_agent_state: StateInspector,
        inspect_approval_state: StateInspector,
    ) -> None:
        self.settings = settings
        self.inspect_agent_state = inspect_agent_state
        self.inspect_approval_state = inspect_approval_state

    async def summary(self, *, include_runtime: bool = False) -> CheckpointDatabaseSummary:
        path = self.settings.langgraph_checkpoint_path
        if not self.settings.langgraph_checkpoint_enabled:
            return CheckpointDatabaseSummary(
                enabled=False,
                path=str(path),
                exists=path.exists(),
                size_bytes=path.stat().st_size if path.exists() else 0,
                thread_count=0,
                checkpoint_count=0,
                write_count=0,
                threads=[],
            )

        with self._connect() as connection:
            checkpoint_count = self._count(connection, "checkpoints")
            write_count = self._count(connection, "writes")
            threads = self._thread_summaries(connection)

        if include_runtime:
            for thread in threads:
                state = await self._inspect_state(thread.thread_id)
                thread.pending = bool(getattr(state, "next", ()))

        return CheckpointDatabaseSummary(
            enabled=True,
            path=str(path),
            exists=path.exists(),
            size_bytes=path.stat().st_size if path.exists() else 0,
            thread_count=len(threads),
            checkpoint_count=checkpoint_count,
            write_count=write_count,
            threads=threads,
        )

    async def cleanup(
        self,
        request: CheckpointCleanupRequest,
    ) -> CheckpointCleanupResult:
        if not self.settings.langgraph_checkpoint_enabled:
            raise ValueError("SQLite 检查点未启用，无需清理")

        path = self.settings.langgraph_checkpoint_path
        with self._connect() as connection:
            before_checkpoints = self._count(connection, "checkpoints")
            before_writes = self._count(connection, "writes")
            thread_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
                )
            ]

            if request.delete_all:
                if request.confirm != "DELETE_ALL":
                    raise ValueError("删除全部检查点时必须提供 confirm=DELETE_ALL")
                delete_ids = thread_ids
            elif request.only_completed:
                delete_ids = []
                for thread_id in thread_ids:
                    state = await self._inspect_state(thread_id)
                    if not bool(getattr(state, "next", ())):
                        delete_ids.append(thread_id)
            else:
                raise ValueError("必须选择仅清理已结束线程，或显式删除全部检查点")

            retained_ids = [
                thread_id for thread_id in thread_ids if thread_id not in delete_ids
            ]
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                for table in self._checkpoint_tables(connection):
                    connection.execute(
                        f"DELETE FROM {table} WHERE thread_id IN ({placeholders})",
                        delete_ids,
                    )

            after_checkpoints = self._count(connection, "checkpoints")
            after_writes = self._count(connection, "writes")

        vacuumed = False
        if request.vacuum and delete_ids:
            with self._connect() as connection:
                connection.execute("VACUUM")
            vacuumed = True

        return CheckpointCleanupResult(
            deleted_thread_ids=delete_ids,
            retained_thread_ids=retained_ids,
            checkpoint_count_before=before_checkpoints,
            checkpoint_count_after=after_checkpoints,
            write_count_before=before_writes,
            write_count_after=after_writes,
            vacuumed=vacuumed,
        )

    async def _inspect_state(self, thread_id: str) -> Any:
        if thread_id.startswith("agent:"):
            return await self.inspect_agent_state(thread_id)
        if thread_id.startswith("tool-approval:"):
            return await self.inspect_approval_state(thread_id)
        raise ValueError(f"无法识别检查点线程类型：{thread_id}")

    @staticmethod
    def _thread_summaries(connection: sqlite3.Connection) -> list[CheckpointThreadSummary]:
        checkpoint_counts = {
            str(thread_id): int(count)
            for thread_id, count in connection.execute(
                "SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id"
            )
        }
        write_counts = {
            str(thread_id): int(count)
            for thread_id, count in connection.execute(
                "SELECT thread_id, COUNT(*) FROM writes GROUP BY thread_id"
            )
        }
        summaries: list[CheckpointThreadSummary] = []
        for thread_id in sorted(checkpoint_counts):
            latest_row = connection.execute(
                """
                SELECT checkpoint_id, metadata
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
            metadata = CheckpointMaintenanceService._parse_metadata(latest_row[1])
            summaries.append(
                CheckpointThreadSummary(
                    thread_id=thread_id,
                    checkpoint_count=checkpoint_counts[thread_id],
                    write_count=write_counts.get(thread_id, 0),
                    latest_checkpoint_id=str(latest_row[0]),
                    latest_source=metadata.get("source") if isinstance(metadata, dict) else None,
                    latest_step=metadata.get("step") if isinstance(metadata, dict) else None,
                )
            )
        return summaries

    @staticmethod
    def _parse_metadata(value: object) -> dict[str, object]:
        if not isinstance(value, bytes):
            return {}
        try:
            import json

            parsed = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _checkpoint_tables(connection: sqlite3.Connection) -> list[str]:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        return [
            table
            for table in ("writes", "checkpoint_blobs", "checkpoints")
            if table in tables
        ]

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.settings.langgraph_checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(path), timeout=30)
