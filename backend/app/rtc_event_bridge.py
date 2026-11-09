from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import time
from typing import Any

import httpx
from pydantic import ValidationError

from .identity import RtcVoiceprintObservation


RTC_OBSERVATION_PATH = "/api/identity/rtc/voiceprint-observations"
RTC_BRIDGE_STATUS_PATH = "/api/identity/rtc/bridge"


class RtcEventBridgeError(RuntimeError):
    """Raised when an RTC event cannot be normalized or delivered safely."""


@dataclass(frozen=True)
class SignedRtcObservation:
    """The exact body and headers sent to the local identity gateway."""

    body: bytes
    timestamp: str
    signature: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Desktop-Pet-Voiceprint-Timestamp": self.timestamp,
            "X-Desktop-Pet-Voiceprint-Signature": self.signature,
        }


def normalize_observation(
    event: RtcVoiceprintObservation | Mapping[str, Any],
) -> RtcVoiceprintObservation:
    """Accept only the already-normalized internal event shape.

    Provider-specific callback fields must be mapped by a separately verified
    RTC worker before reaching this function. Deliberately no aliases or
    fuzzy field lookup are supported here.
    """
    if isinstance(event, RtcVoiceprintObservation):
        observation = event
    elif isinstance(event, Mapping):
        try:
            observation = RtcVoiceprintObservation.model_validate(dict(event))
        except ValidationError as exc:
            raise RtcEventBridgeError(
                "RTC 声纹事件必须包含 task_id、voiceprint_name、voiceprint_score，且不得包含未知字段"
            ) from exc
    else:
        raise RtcEventBridgeError("RTC 声纹事件必须是标准化对象")

    task_id = observation.task_id.strip()
    voiceprint_name = observation.voiceprint_name.strip()
    score = float(observation.voiceprint_score)
    if not task_id or len(task_id) > 128:
        raise RtcEventBridgeError("RTC 任务标识无效")
    if not voiceprint_name or len(voiceprint_name) > 128:
        raise RtcEventBridgeError("RTC 声纹名称无效")
    if not math.isfinite(score) or not 1 <= score <= 100:
        raise RtcEventBridgeError("RTC 声纹分数必须是 1 到 100 之间的有限数字")
    return observation.model_copy(update={
        "task_id": task_id,
        "voiceprint_name": voiceprint_name,
        "voiceprint_score": score,
    })


def sign_observation(
    event: RtcVoiceprintObservation | Mapping[str, Any],
    bridge_secret: str,
    *,
    timestamp: str | None = None,
) -> SignedRtcObservation:
    """Serialize one normalized event and sign the exact bytes sent."""
    secret = bridge_secret.strip()
    if not secret:
        raise RtcEventBridgeError("RTC 声纹桥接密钥未配置")

    observation = normalize_observation(event)
    signed_timestamp = timestamp or str(int(time.time()))
    try:
        int(signed_timestamp)
    except (TypeError, ValueError) as exc:
        raise RtcEventBridgeError("RTC 事件时间戳必须是 Unix 秒级整数") from exc

    body = json.dumps(
        observation.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload = signed_timestamp.encode("ascii") + b"." + body
    signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return SignedRtcObservation(
        body=body,
        timestamp=signed_timestamp,
        signature=signature,
    )


async def submit_observation(
    event: RtcVoiceprintObservation | Mapping[str, Any],
    *,
    bridge_secret: str,
    gateway_url: str = "http://127.0.0.1:8000",
    timeout_seconds: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Submit a signed normalized observation to the local identity gateway."""
    if timeout_seconds <= 0:
        raise RtcEventBridgeError("RTC 事件桥接超时时间必须大于 0")
    signed = sign_observation(event, bridge_secret)
    url = gateway_url.rstrip("/") + RTC_OBSERVATION_PATH
    owns_client = client is None
    request_client = client or httpx.AsyncClient(timeout=timeout_seconds)
    try:
        try:
            response = await request_client.post(
                url,
                content=signed.body,
                headers=signed.headers,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise RtcEventBridgeError("RTC 声纹事件桥接请求超时") from exc
        except httpx.HTTPError as exc:
            raise RtcEventBridgeError("RTC 声纹事件桥接网络不可用") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RtcEventBridgeError(
                f"RTC 声纹事件网关返回了无效 JSON（HTTP {response.status_code}）"
            ) from exc
        if not isinstance(payload, dict):
            raise RtcEventBridgeError("RTC 声纹事件网关返回格式无效")
        if response.status_code >= 400:
            detail = payload.get("detail")
            message = detail if isinstance(detail, str) else payload.get("message")
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("code")
            raise RtcEventBridgeError(
                f"RTC 声纹事件网关拒绝请求（HTTP {response.status_code}"
                + (f"，{message}" if isinstance(message, str) and message else "")
                + "）"
            )
        return payload
    finally:
        if owns_client:
            await request_client.aclose()


async def check_gateway(
    *,
    gateway_url: str = "http://127.0.0.1:8000",
    timeout_seconds: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Check the local gateway's safe RTC bridge readiness response."""
    if timeout_seconds <= 0:
        raise RtcEventBridgeError("RTC 事件桥接超时时间必须大于 0")
    url = gateway_url.rstrip("/") + RTC_BRIDGE_STATUS_PATH
    owns_client = client is None
    request_client = client or httpx.AsyncClient(timeout=timeout_seconds)
    try:
        try:
            response = await request_client.get(url, timeout=timeout_seconds)
        except httpx.TimeoutException as exc:
            raise RtcEventBridgeError("RTC 身份网关启动检查超时") from exc
        except httpx.HTTPError as exc:
            raise RtcEventBridgeError("RTC 身份网关启动检查网络不可用") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RtcEventBridgeError(
                f"RTC 身份网关启动检查返回了无效 JSON（HTTP {response.status_code}）"
            ) from exc
        if not isinstance(payload, dict):
            raise RtcEventBridgeError("RTC 身份网关启动检查返回格式无效")
        if response.status_code >= 400:
            raise RtcEventBridgeError(
                f"RTC 身份网关启动检查失败（HTTP {response.status_code}）"
            )
        if payload.get("identityBridgeConfigured") is not True:
            message = payload.get("message")
            suffix = f"，{message}" if isinstance(message, str) and message else ""
            raise RtcEventBridgeError(f"RTC 身份桥未就绪{suffix}")
        return payload
    finally:
        if owns_client:
            await request_client.aclose()
