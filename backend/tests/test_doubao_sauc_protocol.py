from __future__ import annotations

import gzip
import json
import struct

import pytest

from backend.app.doubao_sauc_protocol import (
    MessageFlags,
    MessageType,
    auth_headers,
    build_audio_packet,
    build_start_packet,
    default_start_payload,
    parse_response,
)


def _response_packet(
    payload: dict[str, object],
    *,
    sequence: int = 2,
    is_last: bool = False,
    message_type: int = MessageType.SERVER_FULL_RESPONSE,
    code: int = 0,
) -> bytes:
    flags = MessageFlags.NEG_WITH_SEQUENCE if is_last else MessageFlags.POS_SEQUENCE
    header = bytes([(1 << 4) | 1, (message_type << 4) | flags, (1 << 4) | 1, 0])
    compressed = gzip.compress(json.dumps(payload).encode())
    if message_type == MessageType.SERVER_ERROR_RESPONSE:
        prefix = struct.pack(">iI", code, len(compressed))
    else:
        prefix = struct.pack(">I", len(compressed))
    return header + struct.pack(">i", sequence) + prefix + compressed


def test_new_api_key_auth_does_not_include_legacy_credentials() -> None:
    headers = auth_headers(
        resource_id="resource",
        api_key="new-key",
        app_key="old-app",
        access_key="old-access",
        request_id="request-id",
    )

    assert headers == {
        "X-Api-Resource-Id": "resource",
        "X-Api-Request-Id": "request-id",
        "X-Api-Key": "new-key",
    }


def test_legacy_auth_requires_both_credentials() -> None:
    headers = auth_headers(
        resource_id="resource",
        app_key="old-app",
        access_key="old-access",
        request_id="request-id",
    )

    assert headers["X-Api-App-Key"] == "old-app"
    assert headers["X-Api-Access-Key"] == "old-access"
    with pytest.raises(ValueError, match="鉴权"):
        auth_headers(resource_id="resource", app_key="old-app")


def test_start_packet_contains_gzip_json_and_positive_sequence() -> None:
    packet = build_start_packet(default_start_payload("desktop-pet", "zh-CN"), sequence=7)

    assert packet[:4] == bytes([
        (1 << 4) | 1,
        (MessageType.CLIENT_FULL_REQUEST << 4) | MessageFlags.POS_SEQUENCE,
        (1 << 4) | 1,
        0,
    ])
    assert struct.unpack(">i", packet[4:8])[0] == 7
    size = struct.unpack(">I", packet[8:12])[0]
    body = json.loads(gzip.decompress(packet[12:12 + size]))
    assert body["user"]["uid"] == "desktop-pet"
    assert body["audio"]["language"] == "zh-CN"


def test_last_audio_packet_uses_negative_sequence() -> None:
    packet = build_audio_packet(b"pcm", sequence=4, is_last=True)

    assert packet[1] == (MessageType.CLIENT_AUDIO_ONLY_REQUEST << 4) | MessageFlags.NEG_WITH_SEQUENCE
    assert struct.unpack(">i", packet[4:8])[0] == -4
    size = struct.unpack(">I", packet[8:12])[0]
    assert gzip.decompress(packet[12:12 + size]) == b"pcm"


def test_parse_partial_final_and_error_responses() -> None:
    partial = parse_response(_response_packet({"result": {"text": "你"}, "additions": {"log_id": "log-1"}}))
    final = parse_response(_response_packet({"result": {"text": "你好"}}, is_last=True))
    error = parse_response(_response_packet(
        {"message": "invalid request"},
        message_type=MessageType.SERVER_ERROR_RESPONSE,
        code=4001,
    ))

    assert partial.text == "你"
    assert partial.log_id == "log-1"
    assert partial.is_last is False
    assert final.text == "你好"
    assert final.is_last is True
    assert error.code == 4001

def test_normalize_sauc_language():
    from backend.app.doubao_sauc_protocol import normalize_sauc_language

    assert normalize_sauc_language("ja") == "ja-JP"
    assert normalize_sauc_language("zh_CN") == "zh-CN"
    assert normalize_sauc_language("en-gb") == "en-GB"
    assert normalize_sauc_language(None) is None

