from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


IdentityStatus = Literal["unknown", "guest", "owner_verified"]
NO_VOICEPRINT_MATCH_NAME = "__no_voiceprint_match__"


class VoiceprintAdapterUnavailableError(RuntimeError):
    """Raised when a production voiceprint provider has not been configured."""


class IdentitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IdentityStatus
    adapter: str
    can_read_private_memory: bool
    can_use_tools: bool
    temporary_open_access: bool
    persistent: bool = False


class RtcVoiceprintObservation(BaseModel):
    """Normalized speaker result emitted by an RTC AI-interaction bridge."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    voiceprint_name: str = Field(min_length=1, max_length=128)
    voiceprint_score: float = Field(ge=1, le=100)


class VoiceprintAdapter(Protocol):
    """Independent speaker-verification boundary for a future real provider."""

    @property
    def name(self) -> str:
        ...

    async def verify(self, audio: bytes) -> bool:
        ...


@dataclass(frozen=True)
class MockVoiceprintAdapter:
    """Deterministic local adapter used until a real voiceprint service is chosen."""

    owner_sample: bytes = b"desktop-pet-mock-owner"

    @property
    def name(self) -> str:
        return "mock"

    async def verify(self, audio: bytes) -> bool:
        return audio == self.owner_sample


@dataclass(frozen=True)
class UnavailableVoiceprintAdapter:
    """Denies verification until a production provider contract is implemented."""

    provider_name: str

    @property
    def name(self) -> str:
        return self.provider_name

    async def verify(self, audio: bytes) -> bool:
        del audio
        raise VoiceprintAdapterUnavailableError("声纹验证服务尚未配置")


@dataclass(frozen=True)
class VolcengineRtcVoiceprintAdapter:
    """Uses verified results from the RTC AI-interaction event stream.

    RTC voiceprint recognition happens inside a VoiceChat task. It is not an
    independent audio-upload API, so raw audio submitted to this gateway must
    not be treated as a production verification attempt.
    """

    owner_name: str
    score_threshold: float

    @property
    def name(self) -> str:
        return "volcengine-rtc"

    async def verify(self, audio: bytes) -> bool:
        del audio
        raise VoiceprintAdapterUnavailableError("RTC 声纹验证需要来自可信 RTC 事件桥的识别结果")

    async def verify_observation(self, observation: RtcVoiceprintObservation) -> bool:
        if observation.voiceprint_name == NO_VOICEPRINT_MATCH_NAME:
            return False
        return (
            observation.voiceprint_name == self.owner_name
            and observation.voiceprint_score >= self.score_threshold
        )


class IdentityService:
    """Keeps the current local identity state and applies the privacy boundary."""

    def __init__(self, adapter: VoiceprintAdapter, temporary_open_access: bool = False):
        self.adapter = adapter
        self.temporary_open_access = temporary_open_access
        self._status: IdentityStatus = "unknown"
        # 持久化验证标志：人脸/密码等非会话式验证通过后置为 True。
        # 为 True 时，声纹会话结束等场景不会自动重置身份状态。
        self._persistent_verified: bool = False
        self._lock = Lock()

    def snapshot(self) -> IdentitySnapshot:
        with self._lock:
            status = self._status
            persistent = self._persistent_verified
        is_owner = self.temporary_open_access or status == "owner_verified"
        effective_status: IdentityStatus = "owner_verified" if is_owner else status
        return IdentitySnapshot(
            status=effective_status,
            adapter=self.adapter.name,
            can_read_private_memory=is_owner,
            can_use_tools=is_owner,
            temporary_open_access=self.temporary_open_access,
            persistent=persistent,
        )

    async def verify(self, audio: bytes) -> IdentitySnapshot:
        if not audio:
            raise ValueError("声纹验证样本不能为空")
        verified = await self.adapter.verify(audio)
        return self.apply_verification(verified)

    async def verify_rtc_observation(self, observation: RtcVoiceprintObservation) -> IdentitySnapshot:
        if not isinstance(self.adapter, VolcengineRtcVoiceprintAdapter):
            raise VoiceprintAdapterUnavailableError("当前身份服务未启用 RTC 声纹适配器")
        verified = await self.adapter.verify_observation(observation)
        return self.apply_verification(verified)

    def apply_verification(self, verified: bool) -> IdentitySnapshot:
        with self._lock:
            self._status = "owner_verified" if verified else "guest"
        return self.snapshot()

    def apply_persistent_verification(self, verified: bool) -> IdentitySnapshot:
        """与 apply_verification 类似，但同时设置持久化标记，
        用于人脸等非会话式验证方式，验证通过后不会因声纹会话结束而被重置。"""
        with self._lock:
            if verified:
                self._status = "owner_verified"
                self._persistent_verified = True
            else:
                self._status = "guest"
                self._persistent_verified = False
        return self.snapshot()

    @property
    def is_persistent(self) -> bool:
        with self._lock:
            return self._persistent_verified

    def reset(self) -> IdentitySnapshot:
        with self._lock:
            self._status = "unknown"
            self._persistent_verified = False
        return self.snapshot()


def owner_required_message() -> dict[str, str]:
    return {
        "code": "OWNER_VERIFICATION_REQUIRED",
        "message": "请先完成主人身份验证",
    }
