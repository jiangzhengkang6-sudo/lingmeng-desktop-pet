from __future__ import annotations

import warnings
from dataclasses import replace

import pytest

from backend.app.agent_workflow.approval_graph import ToolApprovalWorkflow
from backend.app.controlled_tools import (
    ControlledToolService,
    ToolExecuteRequest,
    ToolPolicyError,
)
from backend.app.identity import IdentityService, MockVoiceprintAdapter
from backend.tests.test_agent import configured_settings


@pytest.fixture
def workflow_environment(tmp_path):
    def build(*, checkpoint: bool = False):
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        target_file = allowed_dir / "示例.txt"
        target_file.write_text("测试内容", encoding="utf-8")

        calls: list[dict[str, object]] = []

        def fake_execute(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
            calls.append({"tool_name": tool_name, "arguments": arguments})
            return {"path": arguments["path"], "opened": True}

        settings = replace(
            configured_settings(),
            langgraph_checkpoint_enabled=checkpoint,
            langgraph_checkpoint_path=tmp_path / "langgraph.sqlite3",
        )
        tools = ControlledToolService(
            tmp_path / "tools.sqlite3",
            allowed_directories=(allowed_dir,),
        )
        tools._execute_tool = fake_execute
        identity = IdentityService(
            MockVoiceprintAdapter(),
            temporary_open_access=True,
        )
        workflow = ToolApprovalWorkflow(settings, tools, identity)
        return settings, tools, identity, workflow, calls, target_file

    return build


def open_file_request(
    target_file,
    *,
    idempotency_key: str | None = None,
) -> ToolExecuteRequest:
    return ToolExecuteRequest(
        tool_name="open_file",
        arguments={"path": str(target_file)},
        session_id="approval-session",
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
async def test_open_file_interrupt_can_resume_after_approval(workflow_environment) -> None:
    _, tools, _, workflow, calls, target_file = workflow_environment()

    pending = await workflow.start_open_file(open_file_request(target_file))
    approval = tools.get_approval_by_call_id(pending.call_id)
    final = await workflow.approve(approval.approval_id)

    assert pending.status == "pending"
    assert pending.approval == "pending"
    assert final.status == "success"
    assert final.approval == "approved"
    assert final.result == {"path": str(target_file), "opened": True}
    assert len(calls) == 1

    with pytest.raises(ToolPolicyError) as error:
        await workflow.approve(approval.approval_id)

    assert error.value.code == "APPROVAL_ALREADY_RESOLVED"
    assert error.value.status_code == 409
    assert len(calls) == 1
    await workflow.aclose()


@pytest.mark.asyncio
async def test_open_file_interrupt_can_resume_after_rejection(workflow_environment) -> None:
    _, tools, _, workflow, calls, target_file = workflow_environment()

    pending = await workflow.start_open_file(open_file_request(target_file))
    approval = tools.get_approval_by_call_id(pending.call_id)
    final = await workflow.reject(approval.approval_id)

    assert final.status == "rejected"
    assert final.approval == "rejected"
    assert final.error_code == "APPROVAL_REJECTED"
    assert calls == []

    with pytest.raises(ToolPolicyError) as error:
        await workflow.reject(approval.approval_id)

    assert error.value.code == "APPROVAL_ALREADY_RESOLVED"
    await workflow.aclose()


@pytest.mark.asyncio
async def test_same_idempotency_key_reuses_pending_open_file(workflow_environment) -> None:
    _, tools, _, workflow, calls, target_file = workflow_environment()
    request = open_file_request(target_file, idempotency_key="open-file-key-001")

    first = await workflow.start_open_file(request)
    second = await workflow.start_open_file(request)

    assert first.call_id == second.call_id
    assert first.audit_id == second.audit_id
    assert len(tools.list_approvals(status=None)) == 1
    assert calls == []
    await workflow.aclose()


@pytest.mark.asyncio
async def test_sqlite_checkpoint_supports_resume_without_serde_warning(
    workflow_environment,
) -> None:
    settings, tools, identity, workflow, calls, target_file = workflow_environment(
        checkpoint=True,
    )

    pending = await workflow.start_open_file(
        open_file_request(target_file, idempotency_key="durable-key"),
    )
    approval = tools.get_approval_by_call_id(pending.call_id)
    await workflow.aclose()

    resumed_workflow = ToolApprovalWorkflow(settings, tools, identity)
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        final = await resumed_workflow.approve(approval.approval_id)

    assert final.status == "success"
    assert len(calls) == 1
    assert not any(
        "Deserializing unregistered" in str(record.message)
        for record in records
    )
    await resumed_workflow.aclose()


@pytest.mark.asyncio
async def test_resume_falls_back_to_legacy_when_graph_thread_is_missing(
    workflow_environment,
) -> None:
    _, tools, identity, workflow, calls, target_file = workflow_environment()
    pending = tools.execute(
        open_file_request(target_file),
        identity.snapshot(),
    )
    approval = tools.get_approval_by_call_id(pending.call_id)

    final = await workflow.approve(approval.approval_id)

    assert final.status == "success"
    assert final.approval == "approved"
    assert len(calls) == 1
    await workflow.aclose()
