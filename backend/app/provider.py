from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class SpeechProviderError(Exception):
    def __init__(self, message: str, code: str = "PROVIDER_ERROR", status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class TtsInput:
    text: str
    language: str | None = None
    voice_id: str | None = None
    emotion: str | None = None
    speed: float | None = None
    pitch: float | None = None
    vol: float | None = None


@dataclass(frozen=True)
class AsrInput:
    audio: bytes
    filename: str
    content_type: str
    language: str | None = None


class MiniMaxSpeechProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def synthesize(self, request: TtsInput) -> dict[str, Any]:
        if not self.settings.speech_api_key:
            raise SpeechProviderError("SPEECH_API_KEY 尚未配置", "NOT_CONFIGURED", 503)
        if not request.text.strip():
            raise SpeechProviderError("text 不能为空", "INVALID_REQUEST", 400)

        voice_id = request.voice_id or self.settings.speech_voice_id
        voice_setting: dict[str, Any] = {}
        if voice_id:
            voice_setting["voice_id"] = voice_id
        # speech-2.8-hd 的 speed/pitch/vol 要求使用整数。
        if request.speed is not None:
            voice_setting["speed"] = max(1, min(2, round(request.speed)))
        if request.pitch is not None:
            voice_setting["pitch"] = max(-12, min(12, round(request.pitch)))
        if request.vol is not None:
            voice_setting["vol"] = max(1, min(10, round(request.vol)))
        if request.emotion:
            voice_setting["emotion"] = request.emotion

        body: dict[str, Any] = {
            "model": self.settings.speech_model,
            "text": request.text,
            "stream": False,
            "output_format": "hex",
            "audio_setting": {"format": "mp3"},
        }
        if request.language:
            body["language_boost"] = self._language_boost(request.language)
        if voice_setting:
            body["voice_setting"] = voice_setting

        payload = await self._request_json(
            self.settings.speech_tts_endpoint,
            method="POST",
            json=body,
        )
        base_resp = payload.get("base_resp") or {}
        provider_code = base_resp.get("status_code", 0)
        if provider_code not in (0, "0", None):
            raise SpeechProviderError(
                base_resp.get("status_msg") or "MiniMax 语音合成失败",
                "PROVIDER_ERROR",
                502,
            )

        data = payload.get("data") or {}
        audio = data.get("audio") or payload.get("audio")
        if not audio:
            raise SpeechProviderError("MiniMax 返回中没有音频数据", "INVALID_RESPONSE", 502)
        return {
            "audioHex": audio,
            "mimeType": "audio/mpeg",
            "traceId": payload.get("trace_id"),
        }

    async def transcribe(self, request: AsrInput) -> dict[str, Any]:
        if not self.settings.speech_api_key:
            raise SpeechProviderError("SPEECH_API_KEY 尚未配置", "NOT_CONFIGURED", 503)
        if not self.settings.speech_asr_endpoint:
            raise SpeechProviderError(
                "SPEECH_ASR_ENDPOINT 尚未配置；speech-2.8-hd 仅用于语音合成",
                "NOT_CONFIGURED",
                501,
            )

        data: dict[str, str] = {"model": self.settings.speech_model}
        if request.language:
            data["language"] = request.language
        payload = await self._request_json(
            self.settings.speech_asr_endpoint,
            method="POST",
            data=data,
            files={"file": (request.filename, request.audio, request.content_type)},
        )
        text = payload.get("text")
        if not isinstance(text, str):
            raise SpeechProviderError("语音识别返回中没有 text", "INVALID_RESPONSE", 502)
        return {
            "text": text,
            "language": payload.get("language"),
            "confidence": payload.get("confidence"),
        }

    async def _request_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.speech_api_key}",
            "Accept": "application/json",
        }
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        try:
            if self.client is not None:
                response = await self.client.request(
                    method=kwargs.pop("method"),
                    url=url,
                    headers=headers,
                    timeout=self.settings.speech_timeout_seconds,
                    **kwargs,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method=kwargs.pop("method"),
                        url=url,
                        headers=headers,
                        timeout=self.settings.speech_timeout_seconds,
                        **kwargs,
                    )
        except httpx.TimeoutException as exc:
            raise SpeechProviderError("语音供应商请求超时", "TIMEOUT", 504) from exc
        except httpx.HTTPError as exc:
            raise SpeechProviderError("语音供应商不可用", "NETWORK", 502) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SpeechProviderError("语音供应商返回了无法解析的数据", "INVALID_RESPONSE", 502) from exc
        if response.status_code >= 400:
            message = payload.get("detail") or payload.get("message") or "语音供应商请求失败"
            raise SpeechProviderError(str(message), "PROVIDER_HTTP", 502)
        if not isinstance(payload, dict):
            raise SpeechProviderError("语音供应商返回格式无效", "INVALID_RESPONSE", 502)
        return payload

    @staticmethod
    def _language_boost(language: str) -> str:
        normalized = language.strip().lower().replace("_", "-")
        language_map = {
            "zh": "Chinese",
            "zh-cn": "Chinese",
            "zh-tw": "Chinese",
            "ja": "Japanese",
            "ja-jp": "Japanese",
            "en": "English",
            "en-us": "English",
            "en-gb": "English",
        }
        return language_map.get(normalized, "auto")

