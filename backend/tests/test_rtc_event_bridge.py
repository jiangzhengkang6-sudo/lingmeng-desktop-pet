import hashlib
import hmac
import json

import httpx
import pytest

from backend.app.identity import RtcVoiceprintObservation
from backend.app.rtc_event_bridge import (
    RtcEventBridgeError,
    check_gateway,
    normalize_observation,
    sign_observation,
    submit_observation,
)


def test_normalize_observation_requires_exact_internal_shape() -> None:
    observation = normalize_observation({
        "task_id": "  rtc-task  ",
        "voiceprint_name": "  desktop-owner  ",
        "voiceprint_score": 52,
    })

    assert observation == RtcVoiceprintObservation(
        task_id="rtc-task",
        voiceprint_name="desktop-owner",
        voiceprint_score=52,
    )

    with pytest.raises(RtcEventBridgeError):
        normalize_observation({
            "taskId": "rtc-task",
            "voiceprint_name": "desktop-owner",
            "voiceprint_score": 52,
        })


def test_sign_observation_uses_exact_body_and_timestamp() -> None:
    signed = sign_observation(
        {
            "task_id": "rtc-task",
            "voiceprint_name": "desktop-owner",
            "voiceprint_score": 52,
        },
        "bridge-secret",
        timestamp="1700000000",
    )

    expected_body = (
        b'{"task_id":"rtc-task","voiceprint_name":"desktop-owner","voiceprint_score":52.0}'
    )
    expected_signature = hmac.new(
        b"bridge-secret",
        b"1700000000." + expected_body,
        hashlib.sha256,
    ).hexdigest()
    assert signed.body == expected_body
    assert signed.signature == expected_signature


def test_sign_observation_rejects_invalid_score_and_secret() -> None:
    with pytest.raises(RtcEventBridgeError):
        sign_observation({
            "task_id": "rtc-task",
            "voiceprint_name": "desktop-owner",
            "voiceprint_score": 101,
        }, "bridge-secret")
    with pytest.raises(RtcEventBridgeError):
        sign_observation({
            "task_id": "rtc-task",
            "voiceprint_name": "desktop-owner",
            "voiceprint_score": 52,
        }, "")


@pytest.mark.asyncio
async def test_submit_observation_sends_signed_request_and_returns_gateway_payload() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(200, json={"status": "owner_verified"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = await submit_observation(
        {"task_id": "rtc-task", "voiceprint_name": "desktop-owner", "voiceprint_score": 52},
        bridge_secret="bridge-secret",
        gateway_url="http://gateway.local/",
        client=client,
    )
    await client.aclose()

    assert response == {"status": "owner_verified"}
    assert captured["url"] == "http://gateway.local/api/identity/rtc/voiceprint-observations"
    body = captured["body"]
    headers = captured["headers"]
    assert isinstance(body, bytes)
    assert isinstance(headers, httpx.Headers)
    timestamp = headers["X-Desktop-Pet-Voiceprint-Timestamp"]
    expected = hmac.new(
        b"bridge-secret",
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-Desktop-Pet-Voiceprint-Signature"] == expected
    assert json.loads(body) == {
        "task_id": "rtc-task",
        "voiceprint_name": "desktop-owner",
        "voiceprint_score": 52.0,
    }


@pytest.mark.asyncio
async def test_submit_observation_does_not_swallow_gateway_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            401,
            json={"detail": {"code": "VOICEPRINT_BRIDGE_UNAUTHORIZED", "message": "签名无效"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RtcEventBridgeError, match="HTTP 401"):
        await submit_observation(
            {"task_id": "rtc-task", "voiceprint_name": "desktop-owner", "voiceprint_score": 52},
            bridge_secret="bridge-secret",
            client=client,
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_check_gateway_requires_identity_bridge_configuration() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={
            "identityBridgeConfigured": False,
            "message": "RTC 声纹身份桥尚未完成配置",
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RtcEventBridgeError, match="身份桥未就绪"):
        await check_gateway(client=client)
    await client.aclose()


@pytest.mark.asyncio
async def test_check_gateway_returns_safe_status_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/identity/rtc/bridge")
        return httpx.Response(200, json={
            "identityBridgeConfigured": True,
            "openapiConfigured": True,
            "message": "ready",
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = await check_gateway(
        gateway_url="http://gateway.local/",
        client=client,
    )
    await client.aclose()
    assert response["identityBridgeConfigured"] is True
