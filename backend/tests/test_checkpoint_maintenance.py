from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from backend.app.agent import AgentRequest, AgentService
from backend.app.agent_workflow.approval_graph import ToolApprovalWorkflow
from backend.app.checkpoint_maintenance import (
    CheckpointCleanupRequest,
    CheckpointMaintenanceService,
)
from backend.app.controlled_tools import ControlledToolService, ToolExecuteRequest
from backend.app.identity import IdentityService, MockVoiceprintAdapter
from backend.app.memory import MemoryStore
from backend.tests.test_agent import configured_settings


@pytest.mark.asyncio
async def test_checkpoint_cleanup_keeps_pending_and_deletes_completed(tmp_path) -> None:
    checkpoint_path = tmp_path / "langgraph-checkpoints.sqlite3"
    settings = replace(
        configured_settings(),
        agent_workflow_engine="langgraph",
        agent_provider="mock",
        agent_require_remote=False,
        langgraph_checkpoint_enabled=True,
        langgraph_checkpoint_path=checkpoint_path,
    )
    service = AgentService(
        settings,
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
    )
    await service.respond(AgentRequest(
        message="你好",
        language="zh-CN",
        session_id="completed-session",
    ))

    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    target_file = allowed_dir / "示例.txt"
    target_file.write_text("测试", encoding="utf-8")
    identity = IdentityService(
        MockVoiceprintAdapter(),
        temporary_open_access=True,
    )
    tool_service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_directories=(allowed_dir,),
    )
    approval_workflow = ToolApprovalWorkflow(
        settings,
        tool_service,
        identity,
    )
    pending_result = await approval_workflow.start_open_file(
        ToolExecuteRequest(
            tool_name="open_file",
            arguments={"path": str(target_file)},
            session_id="approval-session",
            idempotency_key="maintenance-pending",
        )
    )

    maintenance = CheckpointMaintenanceService(
        settings,
        service.workflow_runner.get_state_by_thread_id,
        approval_workflow.get_state_by_thread_id,
    )
    summary = await maintenance.summary(include_runtime=True)

    assert summary.enabled is True
    assert summary.exists is True
    assert summary.thread_count == 2
    assert summary.checkpoint_count > 0
    assert summary.write_count > 0
    runtime = {
        thread.thread_id: thread.pending
        for thread in summary.threads
    }
    assert runtime["agent:completed-session"] is False
    approval_thread_id = f"tool-approval:{pending_result.call_id}"
    assert runtime[approval_thread_id] is True
    assert all(
        "你好" not in thread.model_dump_json()
        for thread in summary.threads
    )

    cleanup_result = await maintenance.cleanup(CheckpointCleanupRequest())

    assert cleanup_result.deleted_thread_ids == ["agent:completed-session"]
    assert cleanup_result.retained_thread_ids == [approval_thread_id]
    assert cleanup_result.checkpoint_count_after > 0
    assert cleanup_result.write_count_after > 0
    assert cleanup_result.vacuumed is True

    with sqlite3.connect(checkpoint_path) as connection:
        remaining_threads = [
            row[0]
            for row in connection.execute("SELECT DISTINCT thread_id FROM checkpoints")
        ]
    assert remaining_threads == [approval_thread_id]

    delete_all = await maintenance.cleanup(CheckpointCleanupRequest(
        only_completed=False,
        delete_all=True,
        confirm="DELETE_ALL",
    ))
    assert delete_all.deleted_thread_ids == [approval_thread_id]
    assert delete_all.checkpoint_count_after == 0
    assert delete_all.write_count_after == 0

    await service.close()
    await approval_workflow.aclose()


@pytest.mark.asyncio
async def test_checkpoint_summary_reports_disabled_without_touching_database(tmp_path) -> None:
    settings = replace(
        configured_settings(),
        langgraph_checkpoint_enabled=False,
        langgraph_checkpoint_path=tmp_path / "missing.sqlite3",
    )
    maintenance = CheckpointMaintenanceService(
        settings,
        lambda thread_id: _unreachable(thread_id),
        lambda thread_id: _unreachable(thread_id),
    )

    summary = await maintenance.summary()

    assert summary.enabled is False
    assert summary.exists is False
    assert summary.thread_count == 0
    assert summary.threads == []


async def _unreachable(thread_id: str):
    raise AssertionError(f"不应读取图状态：{thread_id}")
