from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict, Field, field_validator


PET_ACTIONS = frozenset({
    "idle",
    "listening",
    "thinking",
    "speaking",
    "displeased",
    "shy",
    "open-app",
    "working",
    "success",
    "failure",
    "refuse",
    "sleeping",
    "reminder",
})
MOUTH_MODES = frozenset({"closed", "half-open", "open"})


class PetActionEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: str = "pet.action"
    action_id: str = Field(min_length=1, max_length=32, alias="actionId")
    emotion: str | None = Field(default=None, max_length=32)
    mouth_mode: str | None = Field(default=None, max_length=16, alias="mouthMode")
    duration_ms: int | None = Field(default=None, ge=0, le=600_000, alias="durationMs")
    interruptible: bool = True

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != "pet.action":
            raise ValueError("type 必须是 pet.action")
        return value

    @field_validator("action_id")
    @classmethod
    def validate_action_id(cls, value: str) -> str:
        if value not in PET_ACTIONS:
            raise ValueError("不支持的动作")
        return value

    @field_validator("mouth_mode")
    @classmethod
    def validate_mouth_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in MOUTH_MODES:
            raise ValueError("不支持的口型")
        return value

    def wire_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "action_id": self.action_id,
            "emotion": self.emotion,
            "mouth_mode": self.mouth_mode,
            "duration_ms": self.duration_ms,
            "interruptible": self.interruptible,
        }


class PetEventHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, event: PetActionEvent) -> int:
        payload = event.wire_payload()
        async with self._lock:
            clients = tuple(self._clients)

        delivered = 0
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
                delivered += 1
            except Exception:
                stale.append(client)

        for client in stale:
            await self.disconnect(client)
        return delivered
