from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import base64
import binascii
import hmac
import json
import math
from typing import Any, Literal

from .identity import NO_VOICEPRINT_MATCH_NAME, RtcVoiceprintObservation


RTS_SUBTITLE_MAGIC = b"subv"
RTS_VOICEPRINT_STATUS_MAGIC = b"stat"
RTS_HEADER_SIZE = 8
MAX_RTS_MESSAGE_BYTES = 1_000_000

RtsMessageKind = Literal["subtitle", "voiceprint_status"]


class RtsMessageError(ValueError):
    """官方 RTS 消息缺少必要字段或二进制信封不符合协议。"""


class RtsSignatureError(ValueError):
    """官方 RTS 回调签名与 StartVoiceChat 中配置的共享密钥不一致。"""


@dataclass(frozen=True)
class DecodedRtsMessage:
    """一帧已经完成 Base64 和二进制拆包的官方 RTS 消息。"""

    kind: RtsMessageKind
    payload: dict[str, Any]


@dataclass(frozen=True)
class RtsIdentitySelection:
    """从一帧字幕中选出的身份判定结果；没有完整真人句时为空。"""

    observation: RtcVoiceprintObservation | None

    @property
    def has_identity_decision(self) -> bool:
        return self.observation is not None


def verify_rts_signature(signature: str | None, expected_secret: str) -> None:
    """校验官方 RTS 的共享密钥签名。

    火山 RTS 会把 StartVoiceChat 中配置的
    ServerMessageSignatureForRTS 原样放在外层 signature 字段，因此这里使用
    固定时间比较，不把它与本地 HMAC 事件桥密钥混用。
    """
    if not expected_secret or not signature:
        raise RtsSignatureError("RTC RTS 回调签名未配置")
    if not hmac_compare(signature, expected_secret):
        raise RtsSignatureError("RTC RTS 回调签名无效")


def hmac_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def parse_rts_message(body: bytes, *, callback_secret: str) -> DecodedRtsMessage:
    """解析官方 RTS HTTP 回调，但不读取、记录字幕文本。"""
    if not body or len(body) > MAX_RTS_MESSAGE_BYTES:
        raise RtsMessageError("RTC RTS 消息为空或超过大小限制")
    try:
        envelope = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RtsMessageError("RTC RTS 外层消息必须是 JSON 对象") from exc
    if not isinstance(envelope, Mapping):
        raise RtsMessageError("RTC RTS 外层消息必须是 JSON 对象")

    encoded_message = envelope.get("message")
    signature = envelope.get("signature")
    if not isinstance(encoded_message, str) or not encoded_message:
        raise RtsMessageError("RTC RTS message 字段无效")
    if not isinstance(signature, str):
        raise RtsMessageError("RTC RTS signature 字段无效")
    verify_rts_signature(signature, callback_secret)

    try:
        binary_message = base64.b64decode(encoded_message, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RtsMessageError("RTC RTS message 不是合法 Base64") from exc
    return decode_rts_binary(binary_message)


def decode_rts_binary(binary_message: bytes) -> DecodedRtsMessage:
    """拆包 `4 字节 magic + 4 字节大端长度 + UTF-8 JSON`。"""
    if len(binary_message) < RTS_HEADER_SIZE:
        raise RtsMessageError("RTC RTS 二进制消息头不完整")
    magic = binary_message[:4]
    payload_length = int.from_bytes(binary_message[4:8], byteorder="big", signed=False)
    payload_bytes = binary_message[RTS_HEADER_SIZE:]
    if len(payload_bytes) != payload_length:
        raise RtsMessageError("RTC RTS 二进制消息长度不匹配")
    if len(binary_message) > MAX_RTS_MESSAGE_BYTES:
        raise RtsMessageError("RTC RTS 消息超过大小限制")

    if magic == RTS_SUBTITLE_MAGIC:
        kind: RtsMessageKind = "subtitle"
    elif magic == RTS_VOICEPRINT_STATUS_MAGIC:
        kind = "voiceprint_status"
    else:
        raise RtsMessageError("不支持的 RTC RTS 消息类型")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RtsMessageError("RTC RTS JSON 消息体无效") from exc
    if not isinstance(payload, dict):
        raise RtsMessageError("RTC RTS JSON 消息体必须是对象")
    if kind == "subtitle" and payload.get("type") != "subtitle":
        raise RtsMessageError("RTC RTS 字幕消息类型无效")
    return DecodedRtsMessage(kind=kind, payload=payload)


def select_identity_observation(
    subtitle_payload: Mapping[str, Any],
    *,
    task_id: str,
    target_user_ids: Sequence[str],
) -> RtsIdentitySelection:
    """只从完整真人字幕中提取一次身份判定。

    AI 字幕、半句字幕、其他用户字幕均不能授权。完整真人句如果缺少已匹配声纹
    字段，会显式进入未匹配路径，避免旧主人状态残留。
    """
    normalized_task_id = task_id.strip()
    targets = {user_id.strip() for user_id in target_user_ids if isinstance(user_id, str) and user_id.strip()}
    if not normalized_task_id or not targets:
        raise RtsMessageError("RTC RTS 身份判定缺少活动任务或目标用户")
    records = subtitle_payload.get("data")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise RtsMessageError("RTC RTS 字幕 data 必须是数组")

    candidates: list[Mapping[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise RtsMessageError("RTC RTS 字幕 data 项必须是对象")
        user_id = record.get("userId")
        if not isinstance(user_id, str) or user_id.strip() not in targets:
            continue
        if record.get("definite") is not True or record.get("paragraph") is not True:
            continue
        candidates.append(record)

    if not candidates:
        return RtsIdentitySelection(observation=None)
    if len(candidates) > 1:
        raise RtsMessageError("RTC RTS 字幕包含多个目标用户完整句，无法安全关联")

    record = candidates[0]
    voiceprint_name = record.get("voiceprintName")
    voiceprint_score = record.get("voiceprintScore")
    voiceprint_id = record.get("voiceprintId")

    has_matched_voiceprint = (
        isinstance(voiceprint_name, str)
        and bool(voiceprint_name.strip())
        and isinstance(voiceprint_id, str)
        and bool(voiceprint_id.strip())
        and not isinstance(voiceprint_score, bool)
        and isinstance(voiceprint_score, (int, float))
    )
    def is_empty_identity(value: object) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    if is_empty_identity(voiceprint_name) and is_empty_identity(voiceprint_id):
        if voiceprint_score is not None and (
            isinstance(voiceprint_score, bool)
            or not isinstance(voiceprint_score, (int, float))
            or not math.isfinite(float(voiceprint_score))
        ):
            raise RtsMessageError("RTC RTS 声纹分数字段无效")
        unmatched_score = (
            float(voiceprint_score)
            if isinstance(voiceprint_score, (int, float))
            and not isinstance(voiceprint_score, bool)
            and math.isfinite(float(voiceprint_score))
            and 1 <= float(voiceprint_score) <= 100
            else 1
        )
        return RtsIdentitySelection(
            observation=RtcVoiceprintObservation(
                task_id=normalized_task_id,
                voiceprint_name=NO_VOICEPRINT_MATCH_NAME,
                voiceprint_score=unmatched_score,
            )
        )
    if not has_matched_voiceprint:
        raise RtsMessageError("RTC RTS 声纹字段不完整，不能授予主人身份")

    score = float(voiceprint_score)
    name = voiceprint_name.strip()
    if not math.isfinite(score) or not 1 <= score <= 100:
        raise RtsMessageError("RTC RTS 声纹分数必须是 1 到 100 的有限数字")
    observation = RtcVoiceprintObservation(
        task_id=normalized_task_id,
        voiceprint_name=name,
        voiceprint_score=score,
    )
    return RtsIdentitySelection(observation=observation)


def encode_rts_binary(kind: RtsMessageKind, payload: Mapping[str, Any]) -> bytes:
    """供测试和离线工具构造一帧官方二进制消息。"""
    magic = RTS_SUBTITLE_MAGIC if kind == "subtitle" else RTS_VOICEPRINT_STATUS_MAGIC
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return magic + len(body).to_bytes(4, byteorder="big", signed=False) + body
