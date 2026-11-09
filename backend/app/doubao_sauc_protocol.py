from __future__ import annotations

import gzip
import json
import struct
import uuid
from dataclasses import dataclass
from typing import Any


DEFAULT_SAMPLE_RATE = 16_000


class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111


class MessageFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011


def auth_headers(
    *,
    resource_id: str,
    api_key: str = "",
    app_key: str = "",
    access_key: str = "",
    request_id: str | None = None,
) -> dict[str, str]:
    if not api_key and not (app_key and access_key):
        raise ValueError("豆包 ASR 鉴权信息未配置")
    connection_id = request_id or str(uuid.uuid4())
    headers = {
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": connection_id,
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    else:
        headers["X-Api-App-Key"] = app_key
        headers["X-Api-Access-Key"] = access_key
    return headers


def _header(message_type: int, flags: int) -> bytes:
    return bytes([
        (0b0001 << 4) | 1,
        (message_type << 4) | flags,
        (0b0001 << 4) | 0b0001,
        0,
    ])


def _json_payload(payload: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def build_start_packet(payload: dict[str, Any], *, sequence: int = 1) -> bytes:
    compressed = _json_payload(payload)
    return (
        _header(MessageType.CLIENT_FULL_REQUEST, MessageFlags.POS_SEQUENCE)
        + struct.pack(">i", sequence)
        + struct.pack(">I", len(compressed))
        + compressed
    )


def build_audio_packet(audio: bytes, *, sequence: int = 1, is_last: bool = False) -> bytes:
    flags = MessageFlags.NEG_WITH_SEQUENCE if is_last else MessageFlags.POS_SEQUENCE
    compressed = gzip.compress(audio)
    packet_sequence = -sequence if is_last else sequence
    return (
        _header(MessageType.CLIENT_AUDIO_ONLY_REQUEST, flags)
        + struct.pack(">i", packet_sequence)
        + struct.pack(">I", len(compressed))
        + compressed
    )


@dataclass(frozen=True)
class SaucResponse:
    message_type: int
    code: int
    sequence: int | None
    is_last: bool
    event: int | None
    payload: dict[str, Any] | None

    @property
    def text(self) -> str | None:
        result = self.payload.get("result") if self.payload else None
        text = result.get("text") if isinstance(result, dict) else None
        return text if isinstance(text, str) else None

    @property
    def log_id(self) -> str | None:
        additions = self.payload.get("additions") if self.payload else None
        value = additions.get("log_id") if isinstance(additions, dict) else None
        return value if isinstance(value, str) else None


def parse_response(message: bytes) -> SaucResponse:
    if len(message) < 4:
        raise ValueError("豆包 ASR 响应头不完整")
    header_size = message[0] & 0x0F
    header_end = header_size * 4
    if header_size < 1 or len(message) < header_end:
        raise ValueError("豆包 ASR 响应头长度无效")

    message_type = message[1] >> 4
    flags = message[1] & 0x0F
    serialization = message[2] >> 4
    compression = message[2] & 0x0F
    payload = message[header_end:]
    sequence: int | None = None
    event: int | None = None
    is_last = bool(flags & 0b0010)

    if flags & 0b0001:
        if len(payload) < 4:
            raise ValueError("豆包 ASR 响应序列号不完整")
        sequence = struct.unpack(">i", payload[:4])[0]
        payload = payload[4:]
    if flags & 0b0100:
        if len(payload) < 4:
            raise ValueError("豆包 ASR 响应事件号不完整")
        event = struct.unpack(">i", payload[:4])[0]
        payload = payload[4:]

    code = 0
    if message_type == MessageType.SERVER_ERROR_RESPONSE:
        if len(payload) < 8:
            raise ValueError("豆包 ASR 错误响应不完整")
        code, payload_size = struct.unpack(">iI", payload[:8])
        payload = payload[8:8 + payload_size]
    elif message_type == MessageType.SERVER_FULL_RESPONSE:
        if len(payload) < 4:
            raise ValueError("豆包 ASR 响应长度不完整")
        payload_size = struct.unpack(">I", payload[:4])[0]
        payload = payload[4:4 + payload_size]

    if compression == 0b0001 and payload:
        payload = gzip.decompress(payload)
    decoded: dict[str, Any] | None = None
    if serialization == 0b0001 and payload:
        value = json.loads(payload.decode("utf-8"))
        if isinstance(value, dict):
            decoded = value
    return SaucResponse(message_type, code, sequence, is_last, event, decoded)


def normalize_sauc_language(language: str | None) -> str | None:
    if not language:
        return None
    normalized = language.strip().lower().replace("_", "-")
    aliases = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-tw": "zh-TW",
        "ja": "ja-JP",
        "ja-jp": "ja-JP",
        "en": "en-US",
        "en-us": "en-US",
        "en-gb": "en-GB",
    }
    return aliases.get(normalized, normalized)


def default_start_payload(uid: str, language: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user": {"uid": uid},
        "audio": {
            "format": "wav",
            "codec": "raw",
            "rate": DEFAULT_SAMPLE_RATE,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
            "enable_nonstream": False,
        },
    }
    if language:
        payload["audio"]["language"] = normalize_sauc_language(language)
    return payload
