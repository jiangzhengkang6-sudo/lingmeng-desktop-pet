from __future__ import annotations

from typing import TypedDict

from ..agent import (
    AgentRequest,
    AgentResponse,
    AgentSource,
    ConversationMessage,
)
from ..controlled_tools import ToolCallResult, ToolExecuteRequest
from ..identity import IdentitySnapshot
from ..memory import MemoryRecord
from ..persona import PersonaProfile
from ..rag import RagSearchHit


class AgentWorkflowError(TypedDict):
    """可在节点间传递并可被检查点序列化的错误状态。"""

    code: str
    message: str
    status_code: int


class AgentWorkflowState(TypedDict, total=False):
    """一次 Agent 回合在工作流中的状态契约。"""

    request: AgentRequest
    history: tuple[ConversationMessage, ...]
    identity: IdentitySnapshot
    memories: tuple[MemoryRecord, ...]
    persona: PersonaProfile
    sources: list[AgentSource]
    references: tuple[RagSearchHit, ...]
    rag_status: str
    tool_plan: ToolExecuteRequest
    tool_result: ToolCallResult
    response: AgentResponse
    error: AgentWorkflowError

