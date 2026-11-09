from __future__ import annotations

import aiohttp
import pytest

from backend.app.config import Settings
from backend.app.doubao_asr import DoubaoSaucAsr
from backend.app.provider import SpeechProviderError


def configured_settings() -> Settings:
    return Settings(
        speech_provider="minimax",
        speech_model="speech-2.8-hd",
        speech_api_base_url="https://api.minimax.io/v1",
        speech_api_key="minimax-key",
        speech_tts_endpoint="https://api.minimax.io/v1/t2a_v2",
        speech_asr_endpoint="",
        speech_voice_id="",
        speech_timeout_seconds=3.0,
        cors_origins=("http://127.0.0.1:5173",),
        doubao_asr_ws_url="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
        doubao_api_key="doubao-key",
    )


class FailingSession:
    closed = False

    async def ws_connect(self, *_args, **_kwargs):
        raise aiohttp.WSServerHandshakeError(None, (), status=403, message="Forbidden")

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_doubao_handshake_403_is_reported_as_authorization(monkeypatch) -> None:
    session = FailingSession()
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: session)

    with pytest.raises(SpeechProviderError) as error:
        await DoubaoSaucAsr(configured_settings()).start("zh-CN")

    assert error.value.code == "AUTHORIZATION"
    assert error.value.status_code == 502
    assert "key" not in str(error.value).lower()



class RecordingConnection:
    def __init__(self):
        self.packets: list[bytes] = []
        self.closed = False

    async def send_bytes(self, data: bytes) -> None:
        self.packets.append(data)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_stop_does_not_send_duplicate_empty_final_packet():
    settings = configured_settings()
    asr = DoubaoSaucAsr(settings)
    connection = RecordingConnection()
    asr.connection = connection
    asr.started = True
    asr.audio_mode = "wav"

    wav = b"RIFF" + bytes(40) + b"WAVE"
    await asr.send_audio(wav, is_last=True)
    packet_count_after_audio = len(connection.packets)
    await asr.send_audio(b"", is_last=True)

    assert len(connection.packets) == packet_count_after_audio

