from __future__ import annotations

import asyncio
from hashlib import sha256
from typing import Any, Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel

from ..config import Settings
from ..controlled_tools import (
    ControlledToolService,
    ToolCallResult,
    ToolExecuteRequest,
    ToolPolicyError,
)
from ..identity import IdentityService


class ToolApprovalDecision(BaseModel):
    """恢复工具审批图时必须提供的人工决定。"""

    action: Literal["approve", "reject"]
    note: str | None = None


class ToolApprovalState(TypedDict, total=False):
    """open_file 审批工作流状态。"""

    request: ToolExecuteRequest
    call_id: str
    pending_result: ToolCallResult
    final_result: ToolCallResult


class ToolApprovalWorkflow:
    """使用 LangGraph interrupt 表达 open_file 的人工审批。

    该工作流是可选路径：默认关闭时，工具执行和审批仍走原有
    ControlledToolService 接口。审批单、审计和实际打开文件动作仍由
    ControlledToolService 完成，本类只负责暂停、恢复和路由。
    """

    def __init__(
        self,
        settings: Settings,
        tool_service: ControlledToolService,
        identity_service: IdentityService,
    ) -> None:
        self.settings = settings
        self.tool_service = tool_service
        self.identity_service = identity_service
        self._graph: Any | None = None
        self._checkpoint_connection: Any | None = None

    async def start_open_file(self, request: ToolExecuteRequest) -> ToolCallResult:
        call_id = self._call_id(request)
        graph = await self._compiled_graph()
        config = self._config(call_id)

        previous = await graph.aget_state(config)
        existing = self._result_from_values(previous.values)
        if existing is not None:
            return existing

        result = await graph.ainvoke(
            {
                "request": request,
                "call_id": call_id,
            },
            config=config,
        )

        pending_result = result.get("pending_result")
        if not isinstance(pending_result, ToolCallResult):
            raise RuntimeError("工具审批工作流未返回待审批结果")
        return pending_result

    async def approve(self, approval_id: str) -> ToolCallResult:
        return await self._resume(approval_id, "approve")

    async def reject(self, approval_id: str) -> ToolCallResult:
        return await self._resume(approval_id, "reject")

    async def has_workflow_thread(self, call_id: str) -> bool:
        graph = await self._compiled_graph()
        state = await graph.aget_state(self._config(call_id))
        return bool(state.tasks or state.values)

    async def get_state_by_thread_id(self, thread_id: str) -> Any:
        """读取指定审批线程状态，供检查点维护接口识别待审批状态。"""

        graph = await self._compiled_graph()
        return await graph.aget_state({
            "configurable": {
                "thread_id": thread_id,
            },
        })

    async def aclose(self) -> None:
        if self._checkpoint_connection is not None:
            await self._checkpoint_connection.close()
            self._checkpoint_connection = None
        self._graph = None

    async def _resume(
        self,
        approval_id: str,
        action: Literal["approve", "reject"],
    ) -> ToolCallResult:
        approval = await asyncio.to_thread(self.tool_service.get_approval, approval_id)
        if approval.status != "pending":
            raise ToolPolicyError(
                "审批请求已处理",
                "APPROVAL_ALREADY_RESOLVED",
                409,
            )

        graph = await self._compiled_graph()
        config = self._config(approval.call_id)
        state = await graph.aget_state(config)

        # 使用内存检查点且网关重启后，图线程可能已经不存在；审批单仍有效，
        # 此时回退到原有审批方法，避免用户无法处理待审批请求。
        if not isinstance(state.values, dict) or not state.tasks:
            method = (
                self.tool_service.approve
                if action == "approve"
                else self.tool_service.reject
            )
            return await asyncio.to_thread(
                method,
                approval_id,
                self.identity_service.snapshot(),
            )

        from langgraph.types import Command

        result = await graph.ainvoke(
            Command(resume={"action": action}),
            config=config,
        )
        final_result = result.get("final_result")
        if not isinstance(final_result, ToolCallResult):
            raise RuntimeError("工具审批工作流未返回最终结果")
        return final_result

    async def _compiled_graph(self) -> Any:
        if self._graph is not None:
            return self._graph

        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Command, interrupt

        async def create_approval(state: ToolApprovalState) -> dict[str, object]:
            identity = self.identity_service.snapshot()
            pending_result = await asyncio.to_thread(
                self.tool_service.execute,
                state["request"],
                identity,
                state["call_id"],
            )
            if pending_result.status != "pending":
                raise RuntimeError("open_file 应返回待审批状态")
            return {"pending_result": pending_result}

        async def wait_for_decision(state: ToolApprovalState):
            pending_result = state["pending_result"]
            decision = interrupt(
                {
                    "call_id": pending_result.call_id,
                    "tool_name": pending_result.tool_name,
                    "status": pending_result.status,
                    "message": "请确认是否打开该文件",
                },
                response_schema=ToolApprovalDecision,
            )
            if not isinstance(decision, ToolApprovalDecision):
                decision = ToolApprovalDecision.model_validate(decision)
            if decision.action == "approve":
                return Command(goto="批准工具")
            return Command(goto="拒绝工具")

        async def approve_tool(state: ToolApprovalState) -> dict[str, object]:
            identity = self.identity_service.snapshot()
            approval = await asyncio.to_thread(
                self.tool_service.get_approval_by_call_id,
                state["call_id"],
            )
            final_result = await asyncio.to_thread(
                self.tool_service.approve,
                approval.approval_id,
                identity,
            )
            return {"final_result": final_result}

        async def reject_tool(state: ToolApprovalState) -> dict[str, object]:
            identity = self.identity_service.snapshot()
            approval = await asyncio.to_thread(
                self.tool_service.get_approval_by_call_id,
                state["call_id"],
            )
            final_result = await asyncio.to_thread(
                self.tool_service.reject,
                approval.approval_id,
                identity,
            )
            return {"final_result": final_result}

        builder = StateGraph(ToolApprovalState)
        builder.add_node("创建工具审批", create_approval)
        builder.add_node("等待工具审批", wait_for_decision)
        builder.add_node("批准工具", approve_tool)
        builder.add_node("拒绝工具", reject_tool)
        builder.add_edge(START, "创建工具审批")
        builder.add_edge("创建工具审批", "等待工具审批")
        builder.add_edge("批准工具", END)
        builder.add_edge("拒绝工具", END)
        self._graph = builder.compile(checkpointer=await self._create_checkpointer())
        return self._graph

    async def _create_checkpointer(self) -> Any:
        if not self.settings.langgraph_checkpoint_enabled:
            from langgraph.checkpoint.memory import InMemorySaver

            return InMemorySaver()

        import aiosqlite
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        checkpoint_path = self.settings.langgraph_checkpoint_path
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(str(checkpoint_path))
        try:
            serde = JsonPlusSerializer(
                allowed_msgpack_modules=[
                    ("backend.app.controlled_tools", "ToolExecuteRequest"),
                    ("backend.app.controlled_tools", "ToolCallResult"),
                ],
            )
            saver = AsyncSqliteSaver(connection, serde=serde)
            await saver.setup()
        except Exception:
            await connection.close()
            raise
        self._checkpoint_connection = connection
        return saver

    @staticmethod
    def _result_from_values(values: object) -> ToolCallResult | None:
        if not isinstance(values, dict):
            return None
        for name in ("pending_result", "final_result"):
            result = values.get(name)
            if isinstance(result, ToolCallResult):
                return result
        return None

    @staticmethod
    def _call_id(request: ToolExecuteRequest) -> str:
        if not request.idempotency_key:
            return f"tool_{uuid4().hex}"
        material = (
            f"open-file-v1:{request.session_id}:{request.idempotency_key}"
        ).encode("utf-8")
        return f"tool_{sha256(material).hexdigest()[:32]}"

    @staticmethod
    def _config(call_id: str) -> dict[str, object]:
        return {
            "configurable": {
                "thread_id": f"tool-approval:{call_id}",
            },
        }
