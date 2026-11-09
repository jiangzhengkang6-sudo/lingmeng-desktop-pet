from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import Settings
from .state import AgentWorkflowState

if TYPE_CHECKING:
    from ..agent import AgentRequest, AgentResponse


if TYPE_CHECKING:
    from .nodes import AgentWorkflowNodes


class AgentWorkflowError(RuntimeError):
    """工作流执行结果不满足本地契约。"""


class AgentWorkflowRunner:
    """对外提供稳定的工作流执行入口。

    当前图包含上下文组装、本地规划、工具执行、工具回复、远程模型、
    降级处理和后处理节点。旧链路仍由 AgentService 保留，并通过
    AGENT_WORKFLOW_ENGINE 控制是否进入本运行器。
    """

    def __init__(self, settings: Settings, nodes: AgentWorkflowNodes) -> None:
        self.settings = settings
        self._nodes = nodes
        self._graph: Any | None = None
        self._checkpoint_saver: Any | None = None
        self._checkpoint_connection: Any | None = None

    async def run(self, request: AgentRequest) -> AgentResponse:
        graph = await self._compiled_graph()
        result = await graph.ainvoke(
            {"request": request},
            config={
                "configurable": {
                    "thread_id": f"agent:{request.session_id}",
                },
            },
        )

        # 延迟导入，避免工作流模块与 agent.py 在模块加载阶段形成循环依赖。
        from ..agent import AgentResponse

        response = result.get("response")
        if not isinstance(response, AgentResponse):
            raise AgentWorkflowError("工作流未返回有效的 AgentResponse")
        return response

    async def aclose(self) -> None:
        """关闭持久化检查点连接；内存检查点无需额外清理。"""

        if self._checkpoint_connection is not None:
            await self._checkpoint_connection.close()
            self._checkpoint_connection = None
        self._checkpoint_saver = None
        self._graph = None

    async def get_state_by_thread_id(self, thread_id: str) -> Any:
        """读取指定图线程状态，供检查点维护接口判断是否仍在执行。"""

        graph = await self._compiled_graph()
        return await graph.aget_state({
            "configurable": {
                "thread_id": thread_id,
            },
        })

    async def _compiled_graph(self) -> Any:
        if self._graph is not None:
            return self._graph

        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph
        checkpointer = await self._create_checkpointer()

        builder = StateGraph(AgentWorkflowState)
        builder.add_node("上下文组装", self._nodes.assemble_context)
        builder.add_node("本地规划", self._nodes.plan_voice_tool)
        builder.add_node("执行受控工具", self._nodes.execute_controlled_tool)
        builder.add_node("格式化工具回复", self._nodes.format_tool_response)
        builder.add_node("本地模拟应答", self._nodes.call_mock_agent)
        builder.add_node("调用远程模型", self._nodes.call_remote_agent)
        builder.add_node("提供方不可用", self._nodes.mark_unsupported_provider)
        builder.add_node("本地降级应答", self._nodes.fallback_to_mock)
        builder.add_node("显式报错", self._nodes.raise_provider_error)
        builder.add_node("后处理", self._nodes.postprocess)

        builder.add_edge(START, "上下文组装")
        builder.add_edge("上下文组装", "本地规划")
        builder.add_conditional_edges(
            "本地规划",
            self._nodes.route_after_planning,
            {
                "执行受控工具": "执行受控工具",
                "本地模拟应答": "本地模拟应答",
                "调用远程模型": "调用远程模型",
                "提供方不可用": "提供方不可用",
            },
        )
        builder.add_edge("执行受控工具", "格式化工具回复")
        builder.add_edge("格式化工具回复", "后处理")
        builder.add_edge("本地模拟应答", "后处理")
        builder.add_conditional_edges(
            "调用远程模型",
            self._nodes.route_after_remote_agent,
            {
                "后处理": "后处理",
                "本地降级应答": "本地降级应答",
                "显式报错": "显式报错",
            },
        )
        builder.add_conditional_edges(
            "提供方不可用",
            self._nodes.route_provider_error,
            {
                "本地降级应答": "本地降级应答",
                "显式报错": "显式报错",
            },
        )
        builder.add_edge("本地降级应答", "后处理")
        builder.add_edge("后处理", END)
        builder.add_edge("显式报错", END)
        self._graph = builder.compile(checkpointer=checkpointer)
        return self._graph

    async def _create_checkpointer(self) -> Any:
        """按配置创建内存或 SQLite 检查点。

        默认保持内存检查点，避免未审阅前在磁盘上额外持久化会话内容。
        只有显式开启 LANGGRAPH_CHECKPOINT_ENABLED 后才创建 SQLite 文件。
        """

        if not self.settings.langgraph_checkpoint_enabled:
            from langgraph.checkpoint.memory import InMemorySaver

            return InMemorySaver()

        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        checkpoint_path = self.settings.langgraph_checkpoint_path
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(str(checkpoint_path))
        try:
            saver = AsyncSqliteSaver(connection)
            await saver.setup()
        except Exception:
            await connection.close()
            raise
        self._checkpoint_connection = connection
        self._checkpoint_saver = saver
        return saver

