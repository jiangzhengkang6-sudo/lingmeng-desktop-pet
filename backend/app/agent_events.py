from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent import AgentRequest, AgentResponse


AGENT_EVENT_TYPES = frozenset({
    "agent.message",
    "agent.status",
    "agent.response",
    "pet.action",
    "agent.error",
})
AGENT_STATUSES = frozenset({"thinking", "completed"})


class AgentMessageEvent(BaseModel):
    """Client-to-gateway message for the local Agent WebSocket."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["agent.message"]
    request_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4_000)
    language: str = "zh-CN"
    source: Literal["text", "voice"] = "text"
    rag_collection: str | None = None

    @field_validator("request_id", "session_id", "message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value

    def agent_request(self) -> AgentRequest:
        return AgentRequest(
            message=self.message,
            language=self.language,
            session_id=self.session_id,
            source=self.source,
            rag_collection=self.rag_collection,
        )


class AgentStatusEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["agent.status"] = "agent.status"
    request_id: str
    session_id: str
    status: Literal["thinking", "completed"]


class AgentResponseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["agent.response"] = "agent.response"
    request_id: str
    session_id: str
    response: AgentResponse


class AgentPetActionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pet.action"] = "pet.action"
    request_id: str
    session_id: str
    action: dict[str, Any]


class AgentErrorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["agent.error"] = "agent.error"
    request_id: str = ""
    session_id: str = ""
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=256)


AgentServerEvent = (
    AgentStatusEvent
    | AgentResponseEvent
    | AgentPetActionEvent
    | AgentErrorEvent
)
