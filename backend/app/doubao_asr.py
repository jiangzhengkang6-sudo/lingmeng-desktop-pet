from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from .config import Settings
from .audio_format import looks_like_webm, is_wav, pcm_s16le_to_wav
from .doubao_sauc_protocol import (
    MessageType,
    SaucResponse,
    auth_headers,
    build_audio_packet,
    build_start_packet,
    default_start_payload,
    parse_response,
)
from .provider import SpeechProviderError


class DoubaoSaucAsr:
    """One isolated single-direction SAUC upstream connection per browser stream."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session: aiohttp.ClientSession | None = None
        self.connection: aiohttp.ClientWebSocketResponse | None = None
        self.started = False
        self.sequence = 1
        self.audio_mode: str | None = None
        self.pending_pcm = bytearray()
        self.final_sent = False

    @property
    def segment_bytes(self) -> int:
        return max(1, 16_000 * 2 * self.settings.doubao_segment_duration_ms // 1000)

    async def start(self, language: str | None = None) -> None:
        if not self.settings.doubao_asr_configured:
            raise SpeechProviderError("豆包 ASR 尚未配置", "NOT_CONFIGURED", 503)
        self.session = aiohttp.ClientSession()
        try:
            self.connection = await self.session.ws_connect(
                self.settings.doubao_asr_ws_url,
                headers=auth_headers(
                    resource_id=self.settings.doubao_resource_id,
                    api_key=self.settings.doubao_api_key,
                    app_key=self.settings.doubao_app_key,
                    access_key=self.settings.doubao_access_key,
                ),
            )
            await self.connection.send_bytes(
                build_start_packet(
                    default_start_payload(self.settings.doubao_uid, language),
                    sequence=self.sequence,
                )
            )
            self.sequence += 1
            self.started = True
            self.final_sent = False
        except aiohttp.WSServerHandshakeError as exc:
            await self.close()
            if exc.status in (401, 403):
                raise SpeechProviderError(
                    "豆包 ASR 鉴权或资源权限校验失败",
                    "AUTHORIZATION",
                    502,
                ) from exc
            raise SpeechProviderError("豆包 ASR 服务拒绝连接", "PROVIDER_ERROR", 502) from exc
        except aiohttp.ClientError as exc:
            await self.close()
            raise SpeechProviderError("豆包 ASR 服务不可用", "NETWORK", 502) from exc
        except (TimeoutError, ValueError) as exc:
            await self.close()
            raise SpeechProviderError("豆包 ASR 连接失败", "PROVIDER_ERROR", 502) from exc

    async def send_audio(self, audio: bytes, *, is_last: bool = False) -> None:
        if not self.connection or not self.started:
            raise SpeechProviderError("豆包 ASR 流尚未启动", "INVALID_STATE", 409)
        if is_last and self.final_sent:
            # The browser sends a JSON stop command after uploading the WAV.
            # The WAV upload already carries SAUC's negative-sequence final
            # packet, so do not send a second empty final packet with the same
            # sequence number. A duplicate terminal packet can leave upstream
            # emitting partial results without a final response.
            return
        if self.audio_mode is None:
            if is_wav(audio):
                self.audio_mode = "wav"
            elif looks_like_webm(audio):
                raise SpeechProviderError(
                    "豆包单向流需要 WAV 或裸 PCM，暂不支持 WebM 音频",
                    "INVALID_AUDIO_FORMAT",
                    415,
                )
            else:
                self.audio_mode = "pcm"

        if self.audio_mode == "pcm":
            self.pending_pcm.extend(audio)
            if not is_last:
                return
            await self._send_payload(pcm_s16le_to_wav(bytes(self.pending_pcm)), is_last=True)
            self.pending_pcm.clear()
            self.final_sent = True
            return

        await self._send_payload(audio, is_last=is_last)
        if is_last:
            self.final_sent = True

    async def _send_payload(self, audio: bytes, *, is_last: bool) -> None:
        chunks = [
            audio[index:index + self.segment_bytes]
            for index in range(0, len(audio), self.segment_bytes)
        ]
        if not chunks:
            chunks = [b""]
        for index, chunk in enumerate(chunks):
            final_packet = is_last and index == len(chunks) - 1
            await self.connection.send_bytes(
                build_audio_packet(chunk, sequence=self.sequence, is_last=final_packet)
            )
            if not final_packet:
                self.sequence += 1

    async def responses(self) -> AsyncIterator[SaucResponse]:
        if not self.connection:
            return
        try:
            async for message in self.connection:
                if message.type == aiohttp.WSMsgType.BINARY:
                    response = parse_response(message.data)
                    if response.message_type == MessageType.SERVER_ERROR_RESPONSE or response.code:
                        raise SpeechProviderError(
                            "豆包 ASR 返回错误",
                            "PROVIDER_ERROR",
                            502,
                        )
                    yield response
                    if response.is_last:
                        break
                elif message.type == aiohttp.WSMsgType.ERROR:
                    raise SpeechProviderError("豆包 ASR WebSocket 异常", "NETWORK", 502)
                elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    break
        except aiohttp.ClientError as exc:
            raise SpeechProviderError("豆包 ASR WebSocket 不可用", "NETWORK", 502) from exc
        except ValueError as exc:
            raise SpeechProviderError("豆包 ASR 返回格式无效", "INVALID_RESPONSE", 502) from exc

    async def close(self) -> None:
        if self.connection and not self.connection.closed:
            await self.connection.close()
        if self.session and not self.session.closed:
            await self.session.close()
        self.connection = None
        self.session = None
        self.started = False
        self.sequence = 1
        self.audio_mode = None
        self.pending_pcm.clear()
        self.final_sent = False
