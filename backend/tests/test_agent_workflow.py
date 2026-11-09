from dataclasses import replace
import sqlite3

import pytest

from backend.app.agent import (
    AgentProviderError,
    AgentRequest,
    AgentResponse,
    AgentService,
)
from backend.app.controlled_tools import ControlledToolService
from backend.app.memory import MemoryStore

from .test_agent import configured_settings


@pytest.mark.asyncio
async def test_default_agent_service_keeps_legacy_workflow(tmp_path) -> None:
    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="mock",
            agent_require_remote=False,
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
    )

    response = await service.respond(AgentRequest(
        message="你好",
        language="zh-CN",
        session_id="legacy-session",
    ))

    assert response.session_id == "legacy-session"
    assert response.text.startswith("你好")
    assert service.settings.agent_workflow_engine == "legacy"


@pytest.mark.asyncio
async def test_langgraph_workflow_wraps_legacy_turn_without_changing_response(tmp_path) -> None:
    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="mock",
            agent_require_remote=False,
            agent_workflow_engine="langgraph",
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
    )

    response = await service.respond(AgentRequest(
        message="你好",
        language="zh-CN",
        session_id="langgraph-session",
    ))

    assert response.session_id == "langgraph-session"
    assert response.text.startswith("你好")
    assert response.action_id == "speaking"
    assert response.mouth_mode == "half-open"
    assert len(service.conversation_memory.history("langgraph-session")) == 2


@pytest.mark.asyncio
async def test_langgraph_can_persist_state_to_sqlite_checkpoint(tmp_path) -> None:
    checkpoint_path = tmp_path / "langgraph-checkpoints.sqlite3"
    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="mock",
            agent_require_remote=False,
            agent_workflow_engine="langgraph",
            langgraph_checkpoint_enabled=True,
            langgraph_checkpoint_path=checkpoint_path,
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
    )

    response = await service.respond(AgentRequest(
        message="你好",
        language="zh-CN",
        session_id="checkpoint-session",
    ))

    assert response.text.startswith("你好")
    assert checkpoint_path.exists()
    with sqlite3.connect(checkpoint_path) as connection:
        thread_ids = [
            row[0]
            for row in connection.execute("SELECT DISTINCT thread_id FROM checkpoints")
        ]
        write_count = connection.execute(
            "SELECT COUNT(*) FROM writes WHERE thread_id = ?",
            ("agent:checkpoint-session",),
        ).fetchone()[0]

    assert "agent:checkpoint-session" in thread_ids
    assert write_count > 0
    await service.close()


@pytest.mark.asyncio
async def test_langgraph_voice_request_uses_controlled_time_tool(tmp_path) -> None:
    tool_service = ControlledToolService(tmp_path / "tools.sqlite3")
    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="qwen",
            agent_workflow_engine="langgraph",
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
        tool_service=tool_service,
    )

    response = await service.respond(AgentRequest(
        message="现在几点了？",
        language="zh-CN",
        session_id="voice-time-session",
        source="voice",
    ))

    assert response.action_id == "speaking"
    assert response.tool_calls[0]["tool_name"] == "get_time"
    assert response.tool_calls[0]["status"] == "success"


@pytest.mark.asyncio
async def test_langgraph_voice_tool_policy_error_returns_spoken_failure(tmp_path) -> None:
    tool_service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_applications={"记事本": "notepad.exe"},
    )
    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="qwen",
            agent_workflow_engine="langgraph",
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
        tool_service=tool_service,
    )

    response = await service.respond(AgentRequest(
        message="帮我打开记事本",
        language="zh-CN",
        session_id="voice-policy-session",
        source="voice",
    ))

    assert response.action_id == "displeased"
    assert response.tool_calls[0]["status"] == "failure"
    assert response.tool_calls[0]["error_code"] == "OWNER_VERIFICATION_REQUIRED"


@pytest.mark.asyncio
async def test_langgraph_voice_remote_idle_response_is_normalized(tmp_path) -> None:
    class IdleRemoteAgent:
        async def close(self) -> None:
            return None

        async def respond(self, request, *args, **kwargs) -> AgentResponse:
            return AgentResponse(
                session_id=request.session_id,
                text="下午好。",
                language="zh-CN",
                emotion="calm",
                action_id="idle",
                mouth_mode="closed",
                trace_id="agent-idle-1",
            )

    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="qwen",
            agent_workflow_engine="langgraph",
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
        remote_agent=IdleRemoteAgent(),  # type: ignore[arg-type]
    )

    response = await service.respond(AgentRequest(
        message="下午好",
        language="zh-CN",
        session_id="voice-idle-session",
        source="voice",
    ))

    assert response.action_id == "speaking"
    assert response.mouth_mode == "half-open"


@pytest.mark.asyncio
async def test_langgraph_remote_failure_can_fallback_to_mock(tmp_path) -> None:
    class FailingRemoteAgent:
        async def close(self) -> None:
            return None

        async def respond(self, *args, **kwargs) -> AgentResponse:
            raise AgentProviderError("文本 Agent 请求超时", "TIMEOUT", 504)

    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="qwen",
            agent_workflow_engine="langgraph",
            agent_fallback_to_mock=True,
            agent_require_remote=False,
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
        remote_agent=FailingRemoteAgent(),  # type: ignore[arg-type]
    )

    response = await service.respond(AgentRequest(
        message="你好",
        language="zh-CN",
        session_id="fallback-session",
    ))

    assert response.text.startswith("你好")
    assert len(service.conversation_memory.history("fallback-session")) == 2


@pytest.mark.asyncio
async def test_langgraph_remote_failure_raises_when_remote_required(tmp_path) -> None:
    class FailingRemoteAgent:
        async def close(self) -> None:
            return None

        async def respond(self, *args, **kwargs) -> AgentResponse:
            raise AgentProviderError("文本 Agent 请求超时", "TIMEOUT", 504)

    service = AgentService(
        replace(
            configured_settings(),
            agent_provider="qwen",
            agent_workflow_engine="langgraph",
            agent_fallback_to_mock=False,
            agent_require_remote=True,
        ),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
        remote_agent=FailingRemoteAgent(),  # type: ignore[arg-type]
    )

    with pytest.raises(AgentProviderError) as error:
        await service.respond(AgentRequest(
            message="你好",
            language="zh-CN",
            session_id="error-session",
        ))

    assert error.value.code == "TIMEOUT"
    assert service.conversation_memory.history("error-session") == ()

