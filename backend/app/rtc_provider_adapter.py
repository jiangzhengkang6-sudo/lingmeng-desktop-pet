from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any, Protocol

from .identity import NO_VOICEPRINT_MATCH_NAME, RtcVoiceprintObservation
from .rtc_event_bridge import RtcEventBridgeError, normalize_observation


class RtcProviderEventIgnored(RtcEventBridgeError):
    """Raised for known provider events that cannot grant a positive identity state."""

    def __init__(self, message: str, *, observation: RtcVoiceprintObservation | None = None):
        super().__init__(message)
        self.observation = observation


class RtcProviderEventMapper(Protocol):
    """Maps one provider event to the project's normalized voiceprint event."""

    def __call__(
        self,
        event: Mapping[str, Any],
    ) -> RtcVoiceprintObservation | Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class RtcProviderEventAdapter:
    """Fail-closed boundary between a provider SDK and the local identity bridge."""

    provider_name: str
    mapper: RtcProviderEventMapper | None = None

    def adapt(self, event: Mapping[str, Any]) -> RtcVoiceprintObservation:
        if not self.provider_name.strip():
            raise RtcEventBridgeError("RTC 提供商名称未配置")
        if self.mapper is None:
            raise RtcEventBridgeError(
                f"RTC 提供商 {self.provider_name!r} 尚未注册事件映射器；"
                "不能猜测官方回调字段"
            )
        if not isinstance(event, Mapping):
            raise RtcEventBridgeError("RTC 提供商事件必须是 JSON 对象")
        try:
            mapped = self.mapper(event)
        except RtcEventBridgeError:
            raise
        except Exception as exc:
            raise RtcEventBridgeError("RTC 提供商事件映射失败") from exc
        return normalize_observation(mapped)


def reject_asr_payload(event: Mapping[str, Any]) -> RtcVoiceprintObservation:
    """Explicitly reject SAUC/ASR payloads at the voiceprint boundary."""
    del event
    raise RtcEventBridgeError(
        "豆包 SAUC 是语音识别链路，不能转换为 RTC 声纹识别事件"
    )


def map_volcengine_rtc_subtitle_event(
    event: Mapping[str, Any],
    *,
    task_id: str,
) -> RtcVoiceprintObservation:
    """Map one verified Volcengine RTC subtitle callback.

    The provider's subtitle event has no task identifier, so the task ID must
    come from the local RTC worker that started the trusted session. Unknown,
    unmatched, or ambiguous provider data never reaches the identity gateway.
    """
    trusted_task_id = task_id.strip() if isinstance(task_id, str) else ""
    if not trusted_task_id:
        raise RtcEventBridgeError("RTC 官方回调映射需要受信任的 task_id")
    if event.get("type") != "subtitle":
        raise RtcEventBridgeError("仅 subtitle 类型的 RTC 回调可以映射声纹结果")

    records = event.get("data")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise RtcEventBridgeError("RTC subtitle 回调的 data 必须是数组")

    matches: list[tuple[str, float]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise RtcEventBridgeError("RTC subtitle 回调的 data 项必须是对象")

        raw_name = record.get("voiceprintName")
        if raw_name is None:
            continue
        raw_score = record.get("voiceprintScore")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise RtcEventBridgeError("RTC subtitle 回调的 voiceprintName 无效")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            raise RtcEventBridgeError("RTC subtitle 回调的 voiceprintScore 无效")

        score = float(raw_score)
        if not math.isfinite(score):
            raise RtcEventBridgeError("RTC subtitle 回调的 voiceprintScore 必须是有限数字")
        matches.append((raw_name.strip(), score))

    if not matches:
        # 保留固定哨兵值，让可信 worker 可以把“无人匹配”送入安全失败路径；
        # 该值不会出现在用户界面或日志中，也不能通过主人名称校验。
        raise RtcProviderEventIgnored(
            "RTC subtitle 回调未匹配到已注册声纹",
            observation=RtcVoiceprintObservation(
                task_id=trusted_task_id,
                voiceprint_name=NO_VOICEPRINT_MATCH_NAME,
                voiceprint_score=1,
            ),
        )
    if len(matches) != 1:
        raise RtcEventBridgeError("RTC subtitle 回调包含多个声纹匹配结果，无法安全关联")

    voiceprint_name, voiceprint_score = matches[0]
    return RtcVoiceprintObservation(
        task_id=trusted_task_id,
        voiceprint_name=voiceprint_name,
        voiceprint_score=voiceprint_score,
    )


def create_volcengine_rtc_adapter(task_id: str) -> RtcProviderEventAdapter:
    """Create the verified Volcengine RTC callback adapter for one local task."""
    return RtcProviderEventAdapter(
        provider_name="volcengine-rtc",
        mapper=lambda event: map_volcengine_rtc_subtitle_event(event, task_id=task_id),
    )


def create_unconfigured_rtc_adapter(provider_name: str) -> RtcProviderEventAdapter:
    """Create a deliberately unconfigured adapter until an official schema is verified."""
    return RtcProviderEventAdapter(provider_name=provider_name, mapper=None)


__all__ = [
    "RtcProviderEventAdapter",
    "RtcProviderEventIgnored",
    "RtcProviderEventMapper",
    "create_volcengine_rtc_adapter",
    "create_unconfigured_rtc_adapter",
    "map_volcengine_rtc_subtitle_event",
    "reject_asr_payload",
]
