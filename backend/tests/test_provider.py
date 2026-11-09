from __future__ import annotations

import httpx
import pytest

from backend.app.config import Settings
from backend.app.provider import AsrInput, MiniMaxSpeechProvider, SpeechProviderError, TtsInput


def settings(**overrides: str) -> Settings:
    values = {
        "speech_provider": "minimax",
        "speech_model": "speech-2.8-hd",
        "speech_api_base_url": "https://api.minimax.io/v1",
        "speech_api_key": "test-key",
        "speech_tts_endpoint": "https://api.minimaxi.com/v1/t2a_v2",
        "speech_asr_endpoint": "",
        "speech_voice_id": "test-voice",
        "speech_timeout_seconds": 3.0,
        "cors_origins": ("http://127.0.0.1:5173",),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_minimax_tts_request_and_response() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = httpx.Request("POST", "http://test", content=request.content).content
        return httpx.Response(200, json={
            "data": {"audio": "encoded-audio"},
            "trace_id": "trace-1",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MiniMaxSpeechProvider(settings(), client)
        result = await provider.synthesize(TtsInput(text="你好", language="zh-CN"))

    assert result["audioHex"] == "encoded-audio"
    assert result["traceId"] == "trace-1"
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert b'"model":"speech-2.8-hd"' in captured["json"]  # type: ignore[operator]
    assert b'"language_boost":"Chinese"' in captured["json"]  # type: ignore[operator]
    assert b'"output_format":"hex"' in captured["json"]  # type: ignore[operator]
    assert b'"voice_id":"test-voice"' in captured["json"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_provider_error_is_normalized() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "base_resp": {"status_code": 1004, "status_msg": "bad request"},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MiniMaxSpeechProvider(settings(), client)
        with pytest.raises(SpeechProviderError, match="bad request") as error:
            await provider.synthesize(TtsInput(text="test"))

    assert error.value.code == "PROVIDER_ERROR"


@pytest.mark.asyncio
async def test_asr_requires_a_separate_endpoint() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MiniMaxSpeechProvider(settings(), client)
        with pytest.raises(SpeechProviderError) as error:
            await provider.transcribe(AsrInput(b"audio", "speech.webm", "audio/webm"))

    assert error.value.status_code == 501


@pytest.mark.asyncio
async def test_minimax_passes_pitch_and_volume_to_voice_setting():
    calls = []

    class CaptureClient:
        async def request(self, **kwargs):
            calls.append(kwargs)

            class Response:
                status_code = 200

                def json(self):
                    return {"data": {"audio": "abcd"}, "base_resp": {"status_code": 0}}

                async def aclose(self):
                    return None

            return Response()

    settings = Settings(
        speech_provider="minimax",
        speech_model="speech-2.8-hd",
        speech_api_base_url="https://example.invalid",
        speech_api_key="test-key",
        speech_tts_endpoint="https://example.invalid/t2a_v2",
        speech_asr_endpoint=None,
        speech_voice_id="default-voice",
        speech_timeout_seconds=30,
        cors_origins=(),
    )
    provider = MiniMaxSpeechProvider(settings, client=CaptureClient())
    await provider.synthesize(TtsInput(text="你好", voice_id="custom", speed=1.25, pitch=2.4, vol=1.5))

    assert calls
    assert calls[0]["json"]["voice_setting"] == {
        "voice_id": "custom",
        "speed": 1,
        "pitch": 2,
        "vol": 2,
    }
