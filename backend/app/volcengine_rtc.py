from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import math
import secrets
import struct
import time
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import DEFAULT_VOICEPRINT_RTC_API_VERSION, Settings
from .rtc_access_token import AccessToken as OfficialRtcAccessToken, PrivPublishStream, PrivSubscribeStream


RTC_OPENAPI_ENDPOINT = "https://rtc.volcengineapi.com"
RTC_OPENAPI_SERVICE = "rtc"
RTC_VOICEPRINT_ENROLLMENT_API_VERSION = "2024-12-01"


class RtcOpenApiError(RuntimeError):
    def __init__(self, message: str, code: str = "RTC_OPENAPI_ERROR", status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class RtcSessionContextError(RtcOpenApiError):
    """Raised when a task is not part of the current local RTC session set."""


class RtcVoiceChatStartRequest(BaseModel):
    """Runtime values for one explicitly confirmed identity-verification task."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    room_id: str = Field(alias="roomId", min_length=1, max_length=128)
    agent_user_id: str = Field(alias="agentUserId", min_length=1, max_length=128)
    target_user_ids: list[str] = Field(alias="targetUserIds", min_length=1, max_length=16)
    purpose: Literal["identity_verification"] = "identity_verification"
    confirmed: Literal[True]


class RtcVoiceChatSession(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    task_id: str = Field(alias="taskId")
    app_id: str | None = Field(default=None, alias="appId")
    room_id: str | None = Field(default=None, alias="roomId")
    request_id: str | None = Field(default=None, alias="requestId")


class RtcClientJoinToken(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    app_id: str = Field(alias="appId")
    room_id: str = Field(alias="roomId")
    user_id: str = Field(alias="userId")
    token: str
    expires_at_ms: int = Field(alias="expiresAtMs")


class RtcClientTokenRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    task_id: str = Field(alias="taskId", min_length=1, max_length=128)
    user_id: str = Field(alias="userId", min_length=1, max_length=128)
    ttl_seconds: int = Field(default=900, alias="ttlSeconds", ge=60, le=3600)


class RtcVoiceprintBridgeStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider: str
    identity_bridge_configured: bool = Field(alias="identityBridgeConfigured")
    openapi_configured: bool = Field(alias="openapiConfigured")
    scene_configured: bool = Field(alias="sceneConfigured")
    session_control_available: bool = Field(alias="sessionControlAvailable")
    callback_configured: bool = Field(default=False, alias="callbackConfigured")
    client_token_configured: bool = Field(default=False, alias="clientTokenConfigured")
    live_configured: bool = Field(default=False, alias="liveConfigured")
    api_version: str = Field(alias="apiVersion")
    uses_current_api_version: bool = Field(alias="usesCurrentApiVersion")
    message: str


class RtcVoiceprintEnrollment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    voiceprint_id: str = Field(alias="voiceprintId")
    audio_name: str = Field(alias="audioName")
    algorithm_version: int = Field(alias="algorithmVersion")
    scene_updated: bool = Field(alias="sceneUpdated")
    request_id: str | None = Field(default=None, alias="requestId")


@dataclass(frozen=True)
class RtcSceneStore:
    path: Path
    max_bytes: int = 256 * 1024

    def is_available(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise RtcOpenApiError(
                "RTC 声纹场景配置文件不存在",
                "RTC_SCENE_NOT_CONFIGURED",
                503,
            )
        try:
            if self.path.stat().st_size > self.max_bytes:
                raise RtcOpenApiError("RTC 声纹场景配置文件过大", "RTC_SCENE_INVALID", 422)
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            raise RtcOpenApiError("RTC 声纹场景配置不是 UTF-8 JSON", "RTC_SCENE_INVALID", 422) from exc
        except json.JSONDecodeError as exc:
            raise RtcOpenApiError("RTC 声纹场景配置不是有效 JSON", "RTC_SCENE_INVALID", 422) from exc

        if not isinstance(payload, dict):
            raise RtcOpenApiError("RTC 声纹场景配置必须是 JSON 对象", "RTC_SCENE_INVALID", 422)
        self._normalize_voiceprint_score(payload)
        self._validate(payload)
        return payload

    @staticmethod
    def _validate(payload: Mapping[str, Any]) -> None:
        protected_top_level = {"AppId", "RoomId", "TaskId"}
        conflicts = protected_top_level.intersection(payload)
        if conflicts:
            raise RtcOpenApiError(
                f"RTC 场景配置不能覆盖运行时字段：{', '.join(sorted(conflicts))}",
                "RTC_SCENE_INVALID",
                422,
            )
        agent_config = payload.get("AgentConfig")
        if agent_config is not None and not isinstance(agent_config, dict):
            raise RtcOpenApiError("RTC 场景的 AgentConfig 必须是对象", "RTC_SCENE_INVALID", 422)
        if isinstance(agent_config, dict):
            protected_agent_fields = {
                "UserId",
                "TargetUserId",
                "ServerMessageURLForRTS",
                "ServerMessageSignatureForRTS",
            }
            conflicts = protected_agent_fields.intersection(agent_config)
            if conflicts:
                raise RtcOpenApiError(
                    f"RTC 场景的 AgentConfig 不能覆盖运行时字段：{', '.join(sorted(conflicts))}",
                    "RTC_SCENE_INVALID",
                    422,
                )
            voiceprint = agent_config.get("VoicePrint")
            if voiceprint is not None and not isinstance(voiceprint, dict):
                raise RtcOpenApiError(
                    "RTC 场景的 AgentConfig.VoicePrint 必须是对象",
                    "RTC_SCENE_INVALID",
                    422,
                )
            if isinstance(voiceprint, dict) and "Score" in voiceprint:
                score = voiceprint["Score"]
                if (
                    isinstance(score, bool)
                    or not isinstance(score, int)
                    or not 1 <= score <= 100
                ):
                    raise RtcOpenApiError(
                        "RTC 场景的 AgentConfig.VoicePrint.Score 必须是 1 到 100 的整数",
                        "RTC_SCENE_INVALID",
                        422,
                    )
        config = payload.get("Config")
        if config is not None and not isinstance(config, dict):
            raise RtcOpenApiError("RTC 场景的 Config 必须是对象", "RTC_SCENE_INVALID", 422)

    @staticmethod
    def _normalize_voiceprint_score(payload: dict[str, Any]) -> None:
        agent_config = payload.get("AgentConfig")
        if not isinstance(agent_config, dict):
            return
        voiceprint = agent_config.get("VoicePrint")
        if not isinstance(voiceprint, dict) or "Score" not in voiceprint:
            return
        score = voiceprint["Score"]
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not float(score).is_integer()
            or not 1 <= score <= 100
        ):
            raise RtcOpenApiError(
                "RTC 场景的 AgentConfig.VoicePrint.Score 必须是 1 到 100 的整数",
                "RTC_SCENE_INVALID",
                422,
            )
        voiceprint["Score"] = int(score)

    def configure_voiceprint_recognition(self, voiceprint_id: str, score: float) -> None:
        """Write one returned voiceprint ID into a valid recognition scene."""
        normalized_voiceprint_id = voiceprint_id.strip()
        if not normalized_voiceprint_id:
            raise RtcOpenApiError("RTC 声纹 ID 为空", "RTC_VOICEPRINT_INVALID", 422)
        score_payload = {
            "AgentConfig": {
                "VoicePrint": {
                    "Score": score,
                },
            },
        }
        self._normalize_voiceprint_score(score_payload)
        normalized_score = score_payload["AgentConfig"]["VoicePrint"]["Score"]

        payload = self.load() if self.path.is_file() else {}
        self._validate(payload)
        agent_config = _optional_object(payload.get("AgentConfig"), "AgentConfig")
        config = _optional_object(payload.get("Config"), "Config")
        asr_config = _optional_object(config.get("ASRConfig"), "Config.ASRConfig")
        provider_params = _optional_object(
            asr_config.get("ProviderParams"),
            "Config.ASRConfig.ProviderParams",
        )
        voiceprint_config = _optional_object(agent_config.get("VoicePrint"), "AgentConfig.VoicePrint")
        voiceprint_config.pop("EnableSV", None)
        voiceprint_config.update({
            "Mode": 2,
            "IdList": [normalized_voiceprint_id],
            "Score": normalized_score,
        })
        provider_params["StreamMode"] = 0
        asr_config["ProviderParams"] = provider_params
        subtitle_config = _optional_object(config.get("SubtitleConfig"), "Config.SubtitleConfig")
        subtitle_config["SubtitleMode"] = 0
        config["ASRConfig"] = asr_config
        config["SubtitleConfig"] = subtitle_config
        agent_config["VoicePrint"] = voiceprint_config
        agent_config["EnableConversationStateCallback"] = True
        payload.update({"AgentConfig": agent_config, "Config": config})
        self._validate(payload)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


class VolcengineRtcOpenApiClient:
    """Minimal server-side client for the official RTC VoiceChat OpenAPI."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.settings = settings
        self.client = client
        self._owns_client = client is None
        self._now = now or (lambda: datetime.now(UTC))

    async def close(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def start_voice_chat(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request("StartVoiceChat", payload)

    async def stop_voice_chat(self, task_id: str, room_id: str) -> dict[str, Any]:
        return await self._request("StopVoiceChat", {
            "AppId": self.settings.voiceprint_rtc_app_id,
            "RoomId": room_id,
            "TaskId": task_id,
        })

    async def register_voiceprint(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request(
            "RegisterVoicePrint",
            payload,
            api_version=RTC_VOICEPRINT_ENROLLMENT_API_VERSION,
        )

    async def _request(
        self,
        action: str,
        body: Mapping[str, Any],
        *,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.voiceprint_rtc_openapi_configured:
            raise RtcOpenApiError("RTC OpenAPI 尚未完成服务端配置", "RTC_OPENAPI_NOT_CONFIGURED", 503)

        encoded_body = json.dumps(
            dict(body),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        request_url = (
            f"{RTC_OPENAPI_ENDPOINT}?Action={quote(action, safe='')}"
            f"&Version={quote(api_version or self.settings.voiceprint_rtc_api_version, safe='')}"
        )
        headers = self._signed_headers(request_url, encoded_body)
        try:
            if self.client is not None:
                response = await self.client.post(
                    request_url,
                    content=encoded_body,
                    headers=headers,
                    timeout=self.settings.voiceprint_rtc_timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        request_url,
                        content=encoded_body,
                        headers=headers,
                        timeout=self.settings.voiceprint_rtc_timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise RtcOpenApiError("RTC OpenAPI 请求超时", "RTC_OPENAPI_TIMEOUT", 504) from exc
        except httpx.HTTPError as exc:
            raise RtcOpenApiError("RTC OpenAPI 网络不可用", "RTC_OPENAPI_NETWORK", 502) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RtcOpenApiError("RTC OpenAPI 返回了无效 JSON", "RTC_OPENAPI_INVALID_RESPONSE", 502) from exc
        if not isinstance(payload, dict):
            raise RtcOpenApiError("RTC OpenAPI 返回格式无效", "RTC_OPENAPI_INVALID_RESPONSE", 502)

        error = _extract_openapi_error(payload)
        if response.status_code >= 400 or error is not None:
            raise RtcOpenApiError(
                error or "RTC OpenAPI 请求失败",
                "RTC_OPENAPI_PROVIDER_ERROR",
                502,
            )
        return payload

    def _signed_headers(self, request_url: str, body: bytes) -> dict[str, str]:
        parsed = httpx.URL(request_url)
        host = parsed.host.decode("ascii") if isinstance(parsed.host, bytes) else parsed.host
        now = self._now().astimezone(UTC)
        short_date = now.strftime("%Y%m%d")
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_query = parsed.query.decode("ascii")
        canonical_headers = (
            "content-type:application/json\n"
            f"host:{host}\n"
            f"x-content-sha256:{payload_hash}\n"
            f"x-date:{timestamp}\n"
        )
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_request = "\n".join((
            "POST",
            parsed.path or "/",
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ))
        credential_scope = "/".join((
            short_date,
            self.settings.voiceprint_rtc_region,
            RTC_OPENAPI_SERVICE,
            "request",
        ))
        string_to_sign = "\n".join((
            "HMAC-SHA256",
            timestamp,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ))
        signing_key = _signing_key(
            self.settings.voiceprint_rtc_secret_access_key,
            short_date,
            self.settings.voiceprint_rtc_region,
            RTC_OPENAPI_SERVICE,
        )
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "Host": host,
            "X-Date": timestamp,
            "X-Content-Sha256": payload_hash,
            "Authorization": (
                "HMAC-SHA256 "
                f"Credential={self.settings.voiceprint_rtc_access_key_id}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }


class RtcVoiceprintBridge:
    """Loads a local scene and controls a VoiceChat task without exposing secrets."""

    def __init__(
        self,
        settings: Settings,
        client: VolcengineRtcOpenApiClient | None = None,
        scene_store: RtcSceneStore | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.settings = settings
        self.client = client or VolcengineRtcOpenApiClient(settings)
        self.scene_store = scene_store or RtcSceneStore(settings.voiceprint_rtc_scene_path)
        self._clock = clock or time.monotonic
        self._clock_wall = time.time
        self._active_sessions: dict[str, tuple[RtcVoiceChatSession, float]] = {}
        self._session_target_user_ids: dict[str, tuple[str, ...]] = {}
        self._observed_tasks: set[str] = set()

    async def create_client_join_token(
        self,
        *,
        task_id: str,
        user_id: str,
        ttl_seconds: int = 3600,
    ) -> RtcClientJoinToken:
        session = self.require_active_session(task_id)
        normalized_user_id = user_id.strip()
        if not normalized_user_id or len(normalized_user_id) > 128:
            raise RtcOpenApiError("RTC 客户端用户 ID 无效", "INVALID_REQUEST", 422)
        if not 60 <= ttl_seconds <= 24 * 3600:
            raise RtcOpenApiError("RTC Token 有效期必须在 60 秒到 24 小时之间", "INVALID_REQUEST", 422)
        target_user_ids = self._session_target_user_ids.get(_normalize_task_id(task_id), ())
        if normalized_user_id not in target_user_ids:
            raise RtcOpenApiError(
                "RTC 客户端用户 ID 不属于当前验证会话",
                "RTC_CLIENT_USER_NOT_ALLOWED",
                403,
            )
        if not self.settings.voiceprint_rtc_client_token_configured:
            raise RtcOpenApiError(
                "RTC 客户端 Token 尚未配置 AppId 或 AppKey",
                "RTC_CLIENT_TOKEN_NOT_CONFIGURED",
                503,
            )
        room_id = _normalize_room_id(session.room_id)
        expire_time_ms = int((self._clock_wall() + ttl_seconds) * 1000)
        token = _create_official_rtc_access_token(
            app_id=self.settings.voiceprint_rtc_app_id,
            app_key=self.settings.voiceprint_rtc_app_key,
            room_id=room_id,
            user_id=normalized_user_id,
            expire_at=int(expire_time_ms / 1000),
        )
        return RtcClientJoinToken(
            appId=self.settings.voiceprint_rtc_app_id,
            roomId=room_id,
            userId=normalized_user_id,
            token=token,
            expiresAtMs=expire_time_ms,
        )

    async def close(self) -> None:
        self._active_sessions.clear()
        self._session_target_user_ids.clear()
        self._observed_tasks.clear()
        await self.client.close()

    def register_active_session(
        self,
        session: RtcVoiceChatSession,
        target_user_ids: Sequence[str] = (),
    ) -> None:
        """Register only a provider-confirmed session for later event checks."""
        task_id = _normalize_task_id(session.task_id)
        self._purge_expired_sessions()
        if task_id in self._active_sessions:
            raise RtcSessionContextError(
                "RTC 任务已经属于当前活动会话",
                "RTC_SESSION_ALREADY_ACTIVE",
                409,
            )
        self._active_sessions[task_id] = (
            session,
            self._clock() + self.settings.voiceprint_rtc_session_ttl_seconds,
        )
        self._session_target_user_ids[task_id] = tuple(
            user_id.strip()
            for user_id in target_user_ids
            if isinstance(user_id, str) and user_id.strip()
        )

    def claim_observation(self, task_id: str) -> bool:
        """只允许每个本地 RTC 任务消费首个识别结果，防止回放覆盖身份。"""
        normalized_task_id = _normalize_task_id(task_id)
        self.require_active_session(normalized_task_id)
        if normalized_task_id in self._observed_tasks:
            return False
        self._observed_tasks.add(normalized_task_id)
        return True

    def has_active_sessions(self) -> bool:
        self._purge_expired_sessions()
        return bool(self._active_sessions)

    def require_single_active_session(self) -> tuple[RtcVoiceChatSession, tuple[str, ...]]:
        """Return the only active local task for provider push callbacks without task ID."""
        self._purge_expired_sessions()
        if not self._active_sessions:
            raise RtcSessionContextError(
                "RTC RTS 回调不属于当前活动会话，或会话已停止/过期",
                "RTC_SESSION_NOT_ACTIVE",
                409,
            )
        if len(self._active_sessions) != 1:
            raise RtcSessionContextError(
                "存在多个 RTC 活动会话，无法把无任务号的 RTS 回调安全关联",
                "RTC_SESSION_AMBIGUOUS",
                409,
            )
        task_id, (session, _expires_at) = next(iter(self._active_sessions.items()))
        target_user_ids = self._session_target_user_ids.get(task_id, ())
        if not target_user_ids:
            raise RtcSessionContextError(
                "RTC 活动会话缺少目标用户，无法校验声纹字幕来源",
                "RTC_SESSION_INVALID",
                409,
            )
        return session, target_user_ids

    def require_active_session(self, task_id: str) -> RtcVoiceChatSession:
        """Fail closed unless the task was started locally and has not expired."""
        normalized_task_id = _normalize_task_id(task_id)
        self._purge_expired_sessions()
        active = self._active_sessions.get(normalized_task_id)
        if active is None:
            raise RtcSessionContextError(
                "RTC 任务不是当前有效会话，或会话已停止/过期",
                "RTC_SESSION_NOT_ACTIVE",
                409,
            )
        return active[0]

    def status(self) -> RtcVoiceprintBridgeStatus:
        openapi_configured = self.settings.voiceprint_rtc_openapi_configured
        scene_configured = self.scene_store.is_available()
        available = openapi_configured and scene_configured
        if available:
            if self.settings.voiceprint_rtc_api_version == DEFAULT_VOICEPRINT_RTC_API_VERSION:
                message = "RTC 会话控制已配置，仍需由官方 RTC 客户端加入房间并转发识别事件"
            else:
                message = (
                    "RTC 会话控制已配置，但当前 API 版本不是项目默认的 "
                    f"{DEFAULT_VOICEPRINT_RTC_API_VERSION}"
                )
        elif not self.settings.voiceprint_rtc_configured:
            message = "RTC 声纹身份桥尚未完成配置"
        elif not openapi_configured:
            message = "RTC OpenAPI 服务端凭据或 AppId 尚未配置"
        else:
            message = "RTC 声纹场景配置文件尚未创建"
        return RtcVoiceprintBridgeStatus(
            provider=self.settings.voiceprint_provider,
            identityBridgeConfigured=self.settings.voiceprint_rtc_configured,
            openapiConfigured=openapi_configured,
            sceneConfigured=scene_configured,
            sessionControlAvailable=available,
            callbackConfigured=self.settings.voiceprint_rtc_callback_configured,
            clientTokenConfigured=self.settings.voiceprint_rtc_client_token_configured,
            liveConfigured=self.settings.voiceprint_rtc_live_configured and scene_configured,
            apiVersion=self.settings.voiceprint_rtc_api_version,
            usesCurrentApiVersion=(
                self.settings.voiceprint_rtc_api_version == DEFAULT_VOICEPRINT_RTC_API_VERSION
            ),
            message=message,
        )

    async def start_session(self, request: RtcVoiceChatStartRequest) -> RtcVoiceChatSession:
        if not self.settings.voiceprint_rtc_openapi_configured:
            raise RtcOpenApiError("RTC OpenAPI 尚未完成服务端配置", "RTC_OPENAPI_NOT_CONFIGURED", 503)
        scene = self.scene_store.load()
        task_id = _new_task_id()
        payload = _merge_scene(
            scene,
            self.settings.voiceprint_rtc_app_id,
            request,
            task_id=task_id,
            settings=self.settings,
        )
        response = await self.client.start_voice_chat(payload)
        session = _session_from_response(
            response,
            request,
            fallback_task_id=task_id,
        )
        if session.app_id is None:
            session = session.model_copy(update={"appId": self.settings.voiceprint_rtc_app_id})
        self.register_active_session(session, request.target_user_ids)
        return session

    async def stop_session(self, task_id: str) -> RtcVoiceChatSession:
        normalized_task_id = _normalize_task_id(task_id)
        active_session = self.require_active_session(normalized_task_id)
        room_id = _normalize_room_id(active_session.room_id)
        response = await self.client.stop_voice_chat(normalized_task_id, room_id)
        session = _session_from_response(response, None, fallback_task_id=normalized_task_id)
        self._active_sessions.pop(normalized_task_id, None)
        self._active_sessions.pop(session.task_id, None)
        self._session_target_user_ids.pop(normalized_task_id, None)
        self._session_target_user_ids.pop(session.task_id, None)
        self._observed_tasks.discard(normalized_task_id)
        self._observed_tasks.discard(session.task_id)
        return session

    def _purge_expired_sessions(self) -> None:
        now = self._clock()
        expired = [
            task_id
            for task_id, (_, expires_at) in self._active_sessions.items()
            if expires_at <= now
        ]
        for task_id in expired:
            self._active_sessions.pop(task_id, None)
            self._session_target_user_ids.pop(task_id, None)
            self._observed_tasks.discard(task_id)

    async def enroll_owner_voiceprint(self, audio: bytes) -> RtcVoiceprintEnrollment:
        """Register a confirmed owner sample without writing biometric audio to disk."""
        if not self.settings.voiceprint_rtc_openapi_configured:
            raise RtcOpenApiError("RTC OpenAPI 尚未完成服务端配置", "RTC_OPENAPI_NOT_CONFIGURED", 503)
        if self.settings.voiceprint_rtc_score_threshold is None:
            raise RtcOpenApiError("RTC 声纹阈值尚未配置", "RTC_VOICEPRINT_NOT_CONFIGURED", 503)

        response = await self.client.register_voiceprint({
            "AppId": self.settings.voiceprint_rtc_app_id,
            "AudioName": self.settings.voiceprint_rtc_owner_name,
            "AudioFormat": 0,
            "Audio": base64.b64encode(audio).decode("ascii"),
            "Version": 2,
        })
        result = response.get("Result")
        voiceprint_id = result.strip() if isinstance(result, str) else ""
        if not voiceprint_id:
            raise RtcOpenApiError(
                "RTC RegisterVoicePrint 返回中没有 VoicePrintId",
                "RTC_OPENAPI_INVALID_RESPONSE",
                502,
            )

        self.scene_store.configure_voiceprint_recognition(
            voiceprint_id,
            self.settings.voiceprint_rtc_score_threshold,
        )
        return RtcVoiceprintEnrollment(
            voiceprintId=voiceprint_id,
            audioName=self.settings.voiceprint_rtc_owner_name,
            algorithmVersion=2,
            sceneUpdated=True,
            requestId=_request_id(response),
        )


def _merge_scene(
    scene: Mapping[str, Any],
    app_id: str,
    request: RtcVoiceChatStartRequest,
    *,
    task_id: str,
    settings: Settings,
) -> dict[str, Any]:
    payload = dict(scene)
    agent_config = dict(payload.get("AgentConfig") or {})
    config = dict(payload.get("Config") or {})
    subtitle_config = dict(config.get("SubtitleConfig") or {})
    subtitle_config["SubtitleMode"] = 0

    agent_config.update({
        "UserId": request.agent_user_id,
        "TargetUserId": request.target_user_ids,
        "EnableConversationStateCallback": True,
    })
    if settings.voiceprint_rtc_callback_configured:
        agent_config["ServerMessageURLForRTS"] = settings.voiceprint_rtc_callback_url
        agent_config["ServerMessageSignatureForRTS"] = settings.voiceprint_rtc_callback_secret
    config["SubtitleConfig"] = subtitle_config
    payload.update({
        "AppId": app_id,
        "RoomId": request.room_id,
        "TaskId": task_id,
        "AgentConfig": agent_config,
        "Config": config,
    })
    return payload


def _new_task_id() -> str:
    """Create a local-server-owned RTC task ID accepted by the VoiceChat API."""
    return f"desktoppet{uuid4().hex}"


def _session_from_response(
    response: Mapping[str, Any],
    request: RtcVoiceChatStartRequest | None,
    *,
    fallback_task_id: str | None = None,
) -> RtcVoiceChatSession:
    result = response.get("Result")
    result = result if isinstance(result, dict) else response
    task_id = result.get("TaskId") or fallback_task_id
    if not isinstance(task_id, str) or not task_id.strip():
        raise RtcOpenApiError("RTC OpenAPI 返回中没有 TaskId", "RTC_OPENAPI_INVALID_RESPONSE", 502)
    return RtcVoiceChatSession(
        taskId=task_id,
        appId=_optional_string(result.get("AppId")),
        roomId=_optional_string(result.get("RoomId")) or (request.room_id if request else None),
        requestId=_request_id(response),
    )


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_task_id(task_id: str) -> str:
    normalized = task_id.strip() if isinstance(task_id, str) else ""
    if not normalized or len(normalized) > 128:
        raise RtcSessionContextError(
            "RTC 任务标识无效",
            "INVALID_REQUEST",
            422,
        )
    return normalized


def _normalize_room_id(room_id: str | None) -> str:
    normalized = room_id.strip() if isinstance(room_id, str) else ""
    if not normalized or len(normalized) > 128:
        raise RtcSessionContextError(
            "当前 RTC 会话缺少有效房间号，无法安全停止任务",
            "RTC_SESSION_INVALID",
            409,
        )
    return normalized


def _optional_object(value: object, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RtcOpenApiError(
            f"RTC 场景的 {field_name} 必须是对象",
            "RTC_SCENE_INVALID",
            422,
        )
    return dict(value)


def _request_id(response: Mapping[str, Any]) -> str | None:
    metadata = response.get("ResponseMetadata")
    if isinstance(metadata, dict):
        return _optional_string(metadata.get("RequestId"))
    return _optional_string(response.get("RequestId"))


def _extract_openapi_error(payload: Mapping[str, Any]) -> str | None:
    metadata = payload.get("ResponseMetadata")
    if isinstance(metadata, dict):
        error = metadata.get("Error")
        if isinstance(error, dict):
            return _optional_string(error.get("Message")) or _optional_string(error.get("Code"))
    return None


def _create_official_rtc_access_token(
    *,
    app_id: str,
    app_key: str,
    room_id: str,
    user_id: str,
    expire_at: int,
) -> str:
    """Generate a room token using Volcengine's official Python sample algorithm."""
    if len(app_id) != 24:
        raise RtcOpenApiError(
            "RTC AppId 长度必须为 24 位（官方 AccessToken）",
            "RTC_CLIENT_TOKEN_INVALID",
            422,
        )
    if not app_key:
        raise RtcOpenApiError(
            "RTC AppKey 尚未配置",
            "RTC_CLIENT_TOKEN_NOT_CONFIGURED",
            503,
        )
    token = OfficialRtcAccessToken(app_id, app_key, room_id, user_id)
    token.expire_time(expire_at)
    # Voice verification must publish microphone audio and subscribe to RTC state.
    token.add_privilege(PrivPublishStream, 0)
    token.add_privilege(PrivSubscribeStream, 0)
    return token.serialize()


def _create_rtc_access_token(
    *,
    app_id: str,
    app_key: str,
    room_id: str,
    user_id: str,
    expire_at: int,
) -> str:
    """按官方 Web SDK AccessToken 格式签发短期麦克风用户 Token。"""
    if len(app_id) != 24:
        raise RtcOpenApiError(
            "RTC AppId 长度必须为 24 位（官方 AccessToken 前缀固定为 3 位版本号 + 24 位 AppId）",
            "RTC_CLIENT_TOKEN_INVALID",
            422,
        )
    issued_at = int(time.time())
    nonce = secrets.randbits(32)
    # 与官方 rtc-aigc-demo/server/token.js 一致：每个权限的独立过期字段传 0
    # （表示不单独限制），全局过期时间由下方 expire_at 统一控制。
    privileges = {
        0: 0,  # 发布音视频流
        1: 0,  # 发布音频流
        2: 0,  # 发布视频流
        3: 0,  # 发布数据流
        4: 0,  # 订阅流
    }

    def pack_bytes(value: bytes) -> bytes:
        if len(value) > 0xFFFF:
            raise RtcOpenApiError("RTC Token 字段过长", "RTC_CLIENT_TOKEN_INVALID", 422)
        return struct.pack("<H", len(value)) + value

    message = b"".join((
        struct.pack("<I", nonce),
        struct.pack("<I", issued_at),
        struct.pack("<I", expire_at),
        pack_bytes(room_id.encode("utf-8")),
        pack_bytes(user_id.encode("utf-8")),
        struct.pack("<H", len(privileges)),
        b"".join(
            struct.pack("<H", privilege) + struct.pack("<I", privilege_expire)
            for privilege, privilege_expire in privileges.items()
        ),
    ))
    signature = hmac.new(app_key.encode("utf-8"), message, hashlib.sha256).digest()
    content = pack_bytes(message) + pack_bytes(signature)
    return f"001{app_id}{base64.b64encode(content).decode('ascii')}"


def _signing_key(secret: str, short_date: str, region: str, service: str) -> bytes:
    date_key = hmac.new(secret.encode("utf-8"), short_date.encode("ascii"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"request", hashlib.sha256).digest()
