from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..agent import AgentProviderError
from ..controlled_tools import ToolPolicyError
from ..voice_tool_planner import plan_voice_tool
from .state import AgentWorkflowError, AgentWorkflowState

if TYPE_CHECKING:
    from ..agent import AgentService


class AgentWorkflowNodes:
    """LangGraph 中文节点集合。

    节点只编排顺序和条件，不新增安全边界：白名单、身份权限、审计和
    Pydantic 校验仍由原有服务负责。
    """

    def __init__(self, service: AgentService) -> None:
        self.service = service

    async def assemble_context(self, state: AgentWorkflowState) -> dict[str, object]:
        request = state["request"]
        service = self.service
        history = service.conversation_memory.history(request.session_id)
        identity = service.identity_service.snapshot()
        memories = (
            service.memory_store.context(service.settings.memory_context_limit)
            if identity.can_read_private_memory
            else ()
        )
        persona = (
            service.persona_store.get_active()
            if service.persona_store is not None
            else None
        )
        sources, references, rag_status = await service._retrieve_references(request)
        return {
            "history": history,
            "identity": identity,
            "memories": tuple(memories),
            "persona": persona,
            "sources": sources,
            "references": tuple(references),
            "rag_status": rag_status,
        }

    async def plan_voice_tool(self, state: AgentWorkflowState) -> dict[str, object]:
        request = state["request"]
        if request.source != "voice" or self.service.tool_service is None:
            return {"tool_plan": None}

        plan = plan_voice_tool(
            request.message,
            session_id=request.session_id,
            application_names=self.service.tool_service.enabled_application_names(),
        )
        return {"tool_plan": plan.request if plan is not None else None}

    def route_after_planning(self, state: AgentWorkflowState) -> str:
        if state.get("tool_plan") is not None:
            return "执行受控工具"
        provider = self.service.settings.agent_provider
        if provider == "mock":
            return "本地模拟应答"
        if provider in {"qwen", "openai-compatible"}:
            return "调用远程模型"
        return "提供方不可用"

    async def execute_controlled_tool(self, state: AgentWorkflowState) -> dict[str, object]:
        tool_plan = state["tool_plan"]
        identity = state["identity"]
        try:
            tool_result = await asyncio.to_thread(
                self.service.tool_service.execute,
                tool_plan,
                identity,
            )
        except ToolPolicyError as exc:
            tool_result = self.service._tool_policy_failure_result(tool_plan, exc)
        return {"tool_result": tool_result}

    async def format_tool_response(self, state: AgentWorkflowState) -> dict[str, object]:
        response = self.service._voice_tool_response(
            state["request"],
            state["tool_result"],
        )
        return {"response": response}

    async def call_mock_agent(self, state: AgentWorkflowState) -> dict[str, object]:
        response = self.service._mock_response_or_raise(
            state["request"],
            state.get("memories", ()),
            state.get("persona"),
        )
        return {"response": response}

    async def call_remote_agent(self, state: AgentWorkflowState) -> dict[str, object]:
        try:
            response = await self.service.remote_agent.respond(
                state["request"],
                state.get("references", ()),
                state.get("history", ()),
                state.get("memories", ()),
                state.get("persona"),
            )
        except AgentProviderError as exc:
            return {"response": None, "error": self._error(exc)}
        return {"response": response, "error": None}

    def route_after_remote_agent(self, state: AgentWorkflowState) -> str:
        if state.get("response") is not None:
            return "后处理"
        return self.route_provider_error(state)

    async def mark_unsupported_provider(self, state: AgentWorkflowState) -> dict[str, object]:
        error = AgentProviderError(
            "AGENT_PROVIDER 不受支持",
            "NOT_CONFIGURED",
            503,
        )
        return {"error": self._error(error)}

    def route_provider_error(self, state: AgentWorkflowState) -> str:
        settings = self.service.settings
        if settings.agent_require_remote or not settings.agent_fallback_to_mock:
            return "显式报错"
        return "本地降级应答"

    async def fallback_to_mock(self, state: AgentWorkflowState) -> dict[str, object]:
        error = state["error"]
        response = self.service._fallback_or_raise(
            state["request"],
            AgentProviderError(
                error["message"],
                error["code"],
                error["status_code"],
            ),
        )
        return {"response": response}

    async def raise_provider_error(self, state: AgentWorkflowState) -> dict[str, object]:
        error = state["error"]
        raise AgentProviderError(
            error["message"],
            error["code"],
            error["status_code"],
        )

    async def postprocess(self, state: AgentWorkflowState) -> dict[str, object]:
        service = self.service
        request = state["request"]
        identity = state["identity"]
        response = service._with_rag_metadata(
            state["response"],
            state.get("sources", []),
            state.get("rag_status", "disabled"),
        )
        candidates = (
            service.memory_store.create_candidates(
                request.session_id,
                response.memory_candidates,
            )
            if identity.can_read_private_memory
            else []
        )
        response = response.model_copy(update={
            "speaker_identity": identity.status,
            "memory_candidates": candidates,
            "requires_confirmation": response.requires_confirmation or bool(candidates),
        })
        if request.source == "voice" and response.action_id == "idle":
            response = response.model_copy(update={
                "action_id": "speaking",
                "mouth_mode": "half-open" if response.mouth_mode == "closed" else response.mouth_mode,
            })
        service.conversation_memory.append_exchange(
            request.session_id,
            request.message,
            response.text,
        )
        return {"response": response}

    @staticmethod
    def _error(error: AgentProviderError) -> AgentWorkflowError:
        return {
            "code": error.code,
            "message": str(error),
            "status_code": error.status_code,
        }
