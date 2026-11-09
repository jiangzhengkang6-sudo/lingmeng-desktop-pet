from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import io
import json
import os
import time
from typing import Annotated, Any
import wave

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .config import CONFIG_DIRECTORY, Settings
from .agent_workflow.approval_graph import ToolApprovalWorkflow
from .checkpoint_maintenance import (
    CheckpointCleanupRequest,
    CheckpointCleanupResult,
    CheckpointDatabaseSummary,
    CheckpointMaintenanceService,
)
from .agent_events import (
    AgentErrorEvent,
    AgentMessageEvent,
    AgentPetActionEvent,
    AgentResponseEvent,
    AgentStatusEvent,
)
from .controlled_tools import (
    ControlledToolService,
    ToolApproval,
    ToolAuditRecord,
    ToolCallResult,
    ToolDefinition,
    ToolExecuteRequest,
    ToolPolicyError,
)
from .doubao_asr import DoubaoSaucAsr
from .agent import AgentProviderError, AgentRequest, AgentResponse, AgentService
from .identity import (
    IdentityService,
    IdentitySnapshot,
    MockVoiceprintAdapter,
    RtcVoiceprintObservation,
    UnavailableVoiceprintAdapter,
    VolcengineRtcVoiceprintAdapter,
    VoiceprintAdapterUnavailableError,
    owner_required_message,
)
from .local_state import (
    DesktopSettings,
    DesktopSettingsUpdate,
    LocalStateStore,
    LogStatus,
    ReminderCreateRequest,
    ReminderDeleteResponse,
    ReminderDispatcher,
    ReminderRecord,
    ReminderStatus,
    ReminderUpdateRequest,
    SystemLogRecord,
)
from .memory import MemoryCandidate, MemoryDraft, MemoryRecord
from .pet_events import PetActionEvent, PetEventHub
from .provider import AsrInput, MiniMaxSpeechProvider, SpeechProviderError, TtsInput
from .rtc_rts import (
    MAX_RTS_MESSAGE_BYTES,
    RtsMessageError,
    RtsSignatureError,
    parse_rts_message,
    select_identity_observation,
)
from .rag import (
    RagDeleteResponse,
    RagError,
    RagHealthResponse,
    RagIngestResponse,
    RagSearchRequest,
    RagSearchResponse,
    RagService,
)
from .persona import (
    PersonaProfile,
    PersonaProfileDraft,
    PersonaProfileVersion,
    PersonaStore,
)
from .volcengine_rtc import (
    RtcOpenApiError,
    RtcClientJoinToken,
    RtcClientTokenRequest,
    RtcSessionContextError,
    RtcVoiceChatSession,
    RtcVoiceChatStartRequest,
    RtcVoiceprintBridge,
    RtcVoiceprintBridgeStatus,
    RtcVoiceprintEnrollment,
)


settings = Settings.from_environment()
provider = MiniMaxSpeechProvider(settings)
pet_event_hub = PetEventHub()
rag = RagService(settings)
persona_store = PersonaStore(settings.memory_database_path)
agent = AgentService(settings, rag_service=rag, persona_store=persona_store)


def create_voiceprint_adapter(
    settings: Settings,
) -> MockVoiceprintAdapter | UnavailableVoiceprintAdapter | VolcengineRtcVoiceprintAdapter:
    if settings.voiceprint_provider == "mock":
        return MockVoiceprintAdapter()
    if settings.voiceprint_provider == "volcengine-rtc" and settings.voiceprint_rtc_configured:
        assert settings.voiceprint_rtc_score_threshold is not None
        return VolcengineRtcVoiceprintAdapter(
            owner_name=settings.voiceprint_rtc_owner_name,
            score_threshold=settings.voiceprint_rtc_score_threshold,
        )
    return UnavailableVoiceprintAdapter(settings.voiceprint_provider or "unconfigured")


identity = IdentityService(
    create_voiceprint_adapter(settings),
    temporary_open_access=settings.identity_temp_open_access,
)
agent.identity_service = identity
rtc_voiceprint_bridge = RtcVoiceprintBridge(settings)
tools = ControlledToolService(
    settings.tools_database_path,
    allowed_directories=settings.tools_allowed_directories,
    allowed_applications=dict(settings.tools_allowed_applications),
)
agent.tool_service = tools
tool_approval_workflow = ToolApprovalWorkflow(settings, tools, identity)
checkpoint_maintenance = CheckpointMaintenanceService(
    settings,
    agent.workflow_runner.get_state_by_thread_id,
    tool_approval_workflow.get_state_by_thread_id,
)
local_state = LocalStateStore(settings.local_state_database_path)
reminder_dispatcher = ReminderDispatcher(local_state, pet_event_hub.broadcast)

RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES = 1_500_000
RTC_VOICEPRINT_ENROLLMENT_MIN_SECONDS = 15
RTC_VOICEPRINT_ENROLLMENT_MAX_SECONDS = 30
RTC_WAV_CONTENT_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/vnd.wave",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await reminder_dispatcher.start()
    try:
        yield
    finally:
        await reminder_dispatcher.stop()
        await provider.close()
        await agent.close()
        await rag.close()
        await rtc_voiceprint_bridge.close()
        await tool_approval_workflow.aclose()


app = FastAPI(title="灵梦桌宠本地网关", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TtsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(min_length=1, max_length=10_000)
    language: str | None = None
    voice_id: str | None = Field(default=None, alias="voiceId")
    emotion: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    pitch: float | None = Field(default=None, ge=-12, le=12, alias="pitch")
    vol: float | None = Field(default=None, ge=0.1, le=10, alias="vol")


class TtsResponse(BaseModel):
    audioHex: str
    mimeType: str = "audio/mpeg"
    traceId: str | None = None


class AsrResponse(BaseModel):
    text: str
    language: str | None = None
    confidence: float | None = None


class AgentSessionClearResponse(BaseModel):
    session_id: str
    cleared: bool


class MemoryDeleteResponse(BaseModel):
    deleted: bool


class MockIdentityVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample: str = Field(pattern="^(owner|guest)$")


def voiceprint_unavailable_response() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "VOICEPRINT_NOT_CONFIGURED",
            "message": "真实声纹验证尚未配置，请先完成服务端适配器接入",
        },
    )


def voiceprint_bridge_unauthorized_response() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "code": "VOICEPRINT_BRIDGE_UNAUTHORIZED",
            "message": "RTC 声纹事件签名无效或已过期",
        },
    )


def rtc_openapi_error_response(error: RtcOpenApiError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


def rtc_session_context_error_response(error: RtcSessionContextError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


def agent_error_response(error: AgentProviderError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


def validate_rtc_voiceprint_enrollment_audio(content: bytes) -> None:
    """Validate the PCM WAV contract before a biometric cloud upload."""
    if not content:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMPTY_AUDIO", "message": "声纹注册样本不能为空"},
        )
    if len(content) > RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "AUDIO_TOO_LARGE", "message": "声纹注册样本超过大小限制"},
        )
    try:
        with wave.open(io.BytesIO(content), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            compression = wav_file.getcomptype()
    except (EOFError, OSError, ValueError, wave.Error) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_WAV", "message": "声纹注册样本必须是有效 WAV 文件"},
        ) from exc

    if (
        compression != "NONE"
        or channels != 1
        or sample_width != 2
        or frame_rate != 16_000
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_WAV_FORMAT",
                "message": "声纹注册仅支持 16 kHz、16-bit、单声道 PCM WAV",
            },
        )
    duration_seconds = frame_count / frame_rate
    if not RTC_VOICEPRINT_ENROLLMENT_MIN_SECONDS <= duration_seconds <= RTC_VOICEPRINT_ENROLLMENT_MAX_SECONDS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_WAV_DURATION",
                "message": "声纹注册样本时长必须在 15 到 30 秒之间",
            },
        )


def verify_voiceprint_bridge_signature(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
) -> None:
    """Require a short-lived HMAC from the server-side RTC event bridge."""
    if not settings.voiceprint_rtc_configured or not timestamp or not signature:
        raise voiceprint_bridge_unauthorized_response()
    try:
        timestamp_seconds = int(timestamp)
    except ValueError as exc:
        raise voiceprint_bridge_unauthorized_response() from exc
    if abs(time.time() - timestamp_seconds) > settings.voiceprint_rtc_clock_skew_seconds:
        raise voiceprint_bridge_unauthorized_response()
    payload = timestamp.encode("ascii") + b"." + body
    expected = hmac.new(
        settings.voiceprint_rtc_bridge_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise voiceprint_bridge_unauthorized_response()


def require_owner_identity() -> None:
    if not identity.snapshot().can_read_private_memory:
        detail = owner_required_message()
        raise HTTPException(status_code=403, detail=detail)


def record_identity_event(event_type: str, status: LogStatus, message: str) -> None:
    """记录固定安全摘要，避免把凭据、生物音频或完整声纹 ID 写入日志。"""
    try:
        local_state.record_system_event(
            category="identity",
            event_type=event_type,
            status=status,
            message=message,
        )
    except Exception:
        # 日志故障不能改变身份判定或让认证接口泄露内部异常。
        return


def tool_error_response(error: ToolPolicyError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


async def _try_send_agent_event(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    """Send an Agent event, treating a closed client as a normal request end."""
    try:
        await websocket.send_json(payload)
    except (ConnectionError, OSError, RuntimeError, WebSocketDisconnect):
        return False
    return True


@app.get("/api/identity", response_model=IdentitySnapshot)
async def get_identity() -> IdentitySnapshot:
    # 声纹适配器在无活动会话时自动回收验证状态（会话制安全），
    # 但如果是通过人脸等持久化方式验证的，则不应被回收。
    if (
        isinstance(identity.adapter, VolcengineRtcVoiceprintAdapter)
        and not rtc_voiceprint_bridge.has_active_sessions()
        and identity.snapshot().status == "owner_verified"
        and not identity.is_persistent
    ):
        identity.reset()
    return identity.snapshot()


@app.post("/api/identity/mock/verify", response_model=IdentitySnapshot)
async def verify_mock_identity(request: MockIdentityVerificationRequest) -> IdentitySnapshot:
    adapter = identity.adapter
    if not isinstance(adapter, MockVoiceprintAdapter):
        raise HTTPException(
            status_code=503,
            detail={"code": "IDENTITY_ADAPTER_UNAVAILABLE", "message": "本地模拟声纹适配器不可用"},
        )
    sample = adapter.owner_sample if request.sample == "owner" else b"desktop-pet-mock-guest"
    snapshot = await identity.verify(sample)
    record_identity_event(
        "identity.verification_succeeded" if snapshot.status == "owner_verified" else "identity.verification_failed",
        "success" if snapshot.status == "owner_verified" else "warning",
        "本地模拟身份验证完成",
    )
    return snapshot


@app.post("/api/identity/verify", response_model=IdentitySnapshot)
async def verify_identity_audio(
    audio: Annotated[UploadFile, File(...)],
) -> IdentitySnapshot:
    """Verify an in-memory sample without persisting biometric audio locally."""
    if isinstance(identity.adapter, MockVoiceprintAdapter):
        raise voiceprint_unavailable_response()
    content_type = audio.content_type or "application/octet-stream"
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_AUDIO_TYPE", "message": "声纹验证仅接受音频文件"},
        )
    content = await audio.read(settings.voiceprint_max_audio_bytes + 1)
    if not content:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMPTY_AUDIO", "message": "声纹验证样本不能为空"},
        )
    if len(content) > settings.voiceprint_max_audio_bytes:
        raise HTTPException(
            status_code=413,
            detail={"code": "AUDIO_TOO_LARGE", "message": "声纹验证样本超过大小限制"},
        )
    try:
        return await identity.verify(content)
    except VoiceprintAdapterUnavailableError as exc:
        raise voiceprint_unavailable_response() from exc


@app.post("/api/identity/rtc/voiceprint-observations", response_model=IdentitySnapshot)
async def accept_rtc_voiceprint_observation(
    request: Request,
) -> IdentitySnapshot:
    """Accept a signed, normalized result produced by the RTC event bridge."""
    if not isinstance(identity.adapter, VolcengineRtcVoiceprintAdapter):
        raise voiceprint_unavailable_response()
    body = await request.body()
    try:
        verify_voiceprint_bridge_signature(
            body,
            request.headers.get("X-Desktop-Pet-Voiceprint-Timestamp"),
            request.headers.get("X-Desktop-Pet-Voiceprint-Signature"),
        )
    except HTTPException:
        record_identity_event("identity.rtc_observation_rejected", "warning", "RTC 声纹事件签名校验失败")
        raise
    try:
        observation = RtcVoiceprintObservation.model_validate_json(body)
    except ValidationError as exc:
        record_identity_event("identity.rtc_observation_rejected", "warning", "RTC 声纹事件格式无效")
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_VOICEPRINT_OBSERVATION", "message": "RTC 声纹事件格式无效"},
        ) from exc
    try:
        rtc_voiceprint_bridge.require_active_session(observation.task_id)
        if not rtc_voiceprint_bridge.claim_observation(observation.task_id):
            record_identity_event("identity.rtc_observation_rejected", "info", "重复 RTC 声纹事件已忽略")
            return identity.snapshot()
        snapshot = await identity.verify_rtc_observation(observation)
        record_identity_event(
            "identity.verification_succeeded" if snapshot.status == "owner_verified" else "identity.verification_failed",
            "success" if snapshot.status == "owner_verified" else "warning",
            "RTC 声纹识别结果已处理",
        )
        return snapshot
    except RtcSessionContextError as exc:
        record_identity_event("identity.rtc_observation_rejected", "warning", "RTC 声纹事件不属于当前活动会话")
        raise rtc_session_context_error_response(exc) from exc
    except VoiceprintAdapterUnavailableError as exc:
        raise voiceprint_unavailable_response() from exc


@app.post("/api/identity/rtc/voiceprints/register", response_model=RtcVoiceprintEnrollment)
async def register_rtc_owner_voiceprint(
    audio: Annotated[UploadFile, File(...)],
    confirmed: Annotated[bool, Form(...)],
) -> RtcVoiceprintEnrollment:
    """Register one owner-approved WAV sample without persisting its raw audio."""
    if confirmed is not True:
        raise HTTPException(
            status_code=422,
            detail={"code": "CONFIRMATION_REQUIRED", "message": "请确认后再上传声纹注册样本"},
        )
    content_type = (audio.content_type or "").split(";", 1)[0].lower()
    if content_type not in RTC_WAV_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_AUDIO_TYPE", "message": "声纹注册仅接受 WAV 文件"},
        )
    content = await audio.read(RTC_VOICEPRINT_ENROLLMENT_MAX_BYTES + 1)
    validate_rtc_voiceprint_enrollment_audio(content)
    try:
        enrollment = await rtc_voiceprint_bridge.enroll_owner_voiceprint(content)
        record_identity_event("identity.voiceprint_registered", "success", "RTC 声纹注册完成，原始音频未落盘")
        return enrollment
    except RtcOpenApiError as exc:
        record_identity_event("identity.voiceprint_registered", "failure", "RTC 声纹注册失败")
        raise rtc_openapi_error_response(exc) from exc


@app.get("/api/identity/rtc/bridge", response_model=RtcVoiceprintBridgeStatus)
async def get_rtc_voiceprint_bridge_status() -> RtcVoiceprintBridgeStatus:
    """Expose only readiness flags; never return RTC credentials or scene contents."""
    return rtc_voiceprint_bridge.status()


@app.get("/api/identity/rtc/rts/messages")
async def probe_rtc_rts_messages() -> dict[str, bool]:
    """供火山云端在配置回调 URL 时做 GET 连通性检查。"""
    return {"ok": True}


@app.post("/api/identity/rtc/rts/messages")
async def accept_rtc_rts_message(request: Request) -> dict[str, object]:
    """接收火山 RTS 的 subv/stat 二进制信封，不记录原始字幕或声纹 ID。"""
    if not settings.voiceprint_rtc_callback_configured:
        raise HTTPException(
            status_code=503,
            detail={"code": "RTC_RTS_CALLBACK_NOT_CONFIGURED", "message": "RTC RTS 回调尚未配置"},
        )

    body = await request.body()
    if not body or len(body) > MAX_RTS_MESSAGE_BYTES:
        record_identity_event("identity.rts_message_rejected", "warning", "RTC RTS 消息为空或超过大小限制")
        raise HTTPException(
            status_code=413,
            detail={"code": "RTC_RTS_MESSAGE_TOO_LARGE", "message": "RTC RTS 消息超过大小限制"},
        )

    try:
        message = parse_rts_message(
            body,
            callback_secret=settings.voiceprint_rtc_callback_secret,
        )
    except RtsSignatureError as exc:
        record_identity_event("identity.rts_message_rejected", "warning", "RTC RTS 回调签名校验失败")
        raise HTTPException(
            status_code=401,
            detail={"code": "RTC_RTS_SIGNATURE_INVALID", "message": "RTC RTS 回调签名无效"},
        ) from exc
    except RtsMessageError as exc:
        record_identity_event("identity.rts_message_rejected", "warning", "RTC RTS 回调格式无效")
        raise HTTPException(
            status_code=400,
            detail={"code": "RTC_RTS_MESSAGE_INVALID", "message": "RTC RTS 回调格式无效"},
        ) from exc

    if message.kind == "voiceprint_status":
        return {
            "ok": True,
            "kind": "voiceprint_status",
            "identityApplied": False,
        }

    try:
        session, target_user_ids = rtc_voiceprint_bridge.require_single_active_session()
        selection = select_identity_observation(
            message.payload,
            task_id=session.task_id,
            target_user_ids=target_user_ids,
        )
    except RtcSessionContextError as exc:
        record_identity_event("identity.rts_message_rejected", "warning", "RTC RTS 声纹事件不属于当前活动会话")
        raise rtc_session_context_error_response(exc) from exc
    except RtsMessageError as exc:
        record_identity_event("identity.rts_message_rejected", "warning", "RTC RTS 声纹字段格式无效")
        raise HTTPException(
            status_code=400,
            detail={"code": "RTC_RTS_MESSAGE_INVALID", "message": "RTC RTS 声纹字段格式无效"},
        ) from exc

    if selection.observation is None:
        return {
            "ok": True,
            "kind": "subtitle",
            "identityApplied": False,
            "identity": identity.snapshot().model_dump(),
        }

    if not rtc_voiceprint_bridge.claim_observation(session.task_id):
        return {
            "ok": True,
            "kind": "subtitle",
            "identityApplied": False,
            "duplicate": True,
            "identity": identity.snapshot().model_dump(),
        }

    try:
        snapshot = await identity.verify_rtc_observation(selection.observation)
    except VoiceprintAdapterUnavailableError as exc:
        raise voiceprint_unavailable_response() from exc

    record_identity_event(
        "identity.verification_succeeded" if snapshot.status == "owner_verified" else "identity.verification_failed",
        "success" if snapshot.status == "owner_verified" else "warning",
        "RTC RTS 声纹识别结果已处理",
    )
    return {
        "ok": True,
        "kind": "subtitle",
        "identityApplied": True,
        "identity": snapshot.model_dump(),
    }


@app.post("/api/identity/rtc/sessions", response_model=RtcVoiceChatSession)
async def start_rtc_voiceprint_session(
    request: RtcVoiceChatStartRequest,
) -> RtcVoiceChatSession:
    try:
        identity.reset()
        session = await rtc_voiceprint_bridge.start_session(request)
        record_identity_event("identity.rtc_session_started", "success", "RTC 身份验证会话已启动")
        return session
    except RtcOpenApiError as exc:
        record_identity_event("identity.rtc_session_started", "failure", "RTC 身份验证会话启动失败")
        raise rtc_openapi_error_response(exc) from exc


@app.post("/api/identity/rtc/client-token", response_model=RtcClientJoinToken)
async def create_rtc_client_token(
    request: RtcClientTokenRequest,
) -> RtcClientJoinToken:
    """为当前活动验证会话签发短期官方 RTC Web SDK Token。"""
    try:
        return await rtc_voiceprint_bridge.create_client_join_token(
            task_id=request.task_id,
            user_id=request.user_id,
            ttl_seconds=request.ttl_seconds,
        )
    except RtcSessionContextError as exc:
        raise rtc_session_context_error_response(exc) from exc
    except RtcOpenApiError as exc:
        raise rtc_openapi_error_response(exc) from exc


@app.delete("/api/identity/rtc/sessions/{task_id}", response_model=RtcVoiceChatSession)
async def stop_rtc_voiceprint_session(
    task_id: str,
) -> RtcVoiceChatSession:
    normalized_task_id = task_id.strip()
    if not normalized_task_id or len(normalized_task_id) > 128:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_REQUEST", "message": "RTC 任务标识无效"},
        )
    try:
        session = await rtc_voiceprint_bridge.stop_session(normalized_task_id)
        identity.reset()
        record_identity_event("identity.rtc_session_stopped", "success", "RTC 身份验证会话已停止")
        return session
    except RtcSessionContextError as exc:
        record_identity_event("identity.rtc_session_stopped", "warning", "RTC 身份验证会话停止请求无效")
        raise rtc_session_context_error_response(exc) from exc
    except RtcOpenApiError as exc:
        record_identity_event("identity.rtc_session_stopped", "failure", "RTC 身份验证会话停止失败")
        raise rtc_openapi_error_response(exc) from exc


@app.post("/api/identity/reset", response_model=IdentitySnapshot)
async def reset_identity() -> IdentitySnapshot:
    snapshot = identity.reset()
    record_identity_event("identity.verification_reset", "info", "身份状态已重置")
    return snapshot


# ─── 人脸识别身份认证 ────────────────────────────────────────


class FaceStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    has_profile: bool
    similarity_threshold: float
    min_samples: int
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class FaceRegisterRequest(BaseModel):
    name: str = "owner"


class FaceProfileResponse(BaseModel):
    name: str
    sample_count: int
    created_at: float


def _face_engine():
    """懒加载人脸识别引擎。"""
    from .face_recognition import (
        FaceProfileStore,
        FaceVerificationAdapter,
        SFaceFaceEngine,
        SFACE_MODEL_FILENAME,
        YUNET_MODEL_FILENAME,
        resolve_model_path,
    )

    if not settings.face_recognition_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FACE_RECOGNITION_DISABLED",
                "message": "人脸识别功能未启用",
                "diagnostics": _face_diagnostics(),
            },
        )
    detector_path = resolve_model_path(
        settings.face_detection_model_path, CONFIG_DIRECTORY, YUNET_MODEL_FILENAME
    )
    recognizer_path = resolve_model_path(
        settings.face_recognizer_model_path, CONFIG_DIRECTORY, SFACE_MODEL_FILENAME
    )
    if not (os.path.isfile(detector_path) and os.path.isfile(recognizer_path)):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FACE_MODEL_MISSING",
                "message": "人脸检测/识别模型缺失，请查看 diagnostics.models 中的候选路径",
                "diagnostics": _face_diagnostics(),
            },
        )
    engine = SFaceFaceEngine.get(detector_path, recognizer_path)
    store = FaceProfileStore(settings.face_recognition_profile_path)
    adapter = FaceVerificationAdapter(
        engine=engine,
        profile_store=store,
        similarity_threshold=settings.face_recognition_similarity_threshold,
        min_reference_samples=settings.face_recognition_min_samples,
        name="sface-face",
    )
    return engine, adapter, store


def _face_model_available() -> bool:
    """检查人脸模型文件是否可用（兼容打包后路径）。"""
    from .face_recognition import SFACE_MODEL_FILENAME, YUNET_MODEL_FILENAME, resolve_model_path

    detector = resolve_model_path(
        settings.face_detection_model_path, CONFIG_DIRECTORY, YUNET_MODEL_FILENAME
    )
    recognizer = resolve_model_path(
        settings.face_recognizer_model_path, CONFIG_DIRECTORY, SFACE_MODEL_FILENAME
    )
    return os.path.isfile(detector) and os.path.isfile(recognizer)


def _face_diagnostics() -> dict[str, Any]:
    """返回人脸模块路径、依赖和运行时诊断，避免线上 503 只能盲猜。"""
    from .face_recognition import face_runtime_diagnostics

    return face_runtime_diagnostics(
        {
            "detector_yunet": settings.face_detection_model_path,
            "recognizer_sface": settings.face_recognizer_model_path,
            "landmarker_mediapipe": settings.face_recognition_model_path,
        },
        CONFIG_DIRECTORY,
        required_dependencies=("cv2",),
        optional_dependencies=("mediapipe",),
    )


@app.get("/api/face/status", response_model=FaceStatusResponse)
async def face_status() -> FaceStatusResponse:
    from .face_recognition import FaceProfileStore

    store = FaceProfileStore(settings.face_recognition_profile_path)
    diagnostics = _face_diagnostics()
    if not settings.face_recognition_enabled:
        return FaceStatusResponse(
            enabled=False,
            configured=False,
            has_profile=False,
            similarity_threshold=settings.face_recognition_similarity_threshold,
            min_samples=settings.face_recognition_min_samples,
            diagnostics=diagnostics,
        )
    return FaceStatusResponse(
        enabled=True,
        configured=all(
            model["path"] is not None
            for role, model in diagnostics["models"].items()
            if role in {"detector_yunet", "recognizer_sface"}
        ),
        has_profile=store.load() is not None,
        similarity_threshold=settings.face_recognition_similarity_threshold,
        min_samples=settings.face_recognition_min_samples,
        diagnostics=diagnostics,
    )


@app.post("/api/face/register", response_model=FaceProfileResponse)
async def face_register(
    name: Annotated[str, Form(...)] = "owner",
    images: Annotated[list[UploadFile], File(...)] = [],
) -> FaceProfileResponse:
    """用多张图片注册主人人脸。"""
    from .face_recognition import FaceRecognitionError

    _, adapter, _ = _face_engine()
    samples: list[bytes] = []
    for img in images:
        data = await img.read(10 * 1024 * 1024)  # 单张上限 10MB
        if data:
            samples.append(data)
    try:
        profile = adapter.register_samples(name=name, image_samples=samples)
    except FaceRecognitionError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "FACE_REGISTRATION_FAILED", "message": str(exc)},
        ) from exc
    record_identity_event(
        "identity.face_registered", "success", f"人脸注册完成：{name}（{len(profile.features)} 张样本）"
    )
    return FaceProfileResponse(
        name=profile.name,
        sample_count=len(profile.features),
        created_at=profile.created_at,
    )


@app.post("/api/face/verify", response_model=IdentitySnapshot)
async def face_verify(image: Annotated[UploadFile, File(...)]) -> IdentitySnapshot:
    """用人脸图片验证主人身份。"""
    from .face_recognition import FaceRecognitionError

    _, adapter, _ = _face_engine()
    image_data = await image.read(10 * 1024 * 1024)
    if not image_data:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMPTY_IMAGE", "message": "图片为空"},
        )
    try:
        verified = await adapter.verify(image_data)
    except FaceRecognitionError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "FACE_VERIFICATION_FAILED", "message": str(exc)},
        ) from exc
    # 人脸验证是持久化的（非会话制），验证通过后不因声纹会话结束而掉权限。
    snapshot = identity.apply_persistent_verification(verified)
    record_identity_event(
        "identity.face_verification_succeeded" if verified else "identity.face_verification_failed",
        "success" if verified else "warning",
        "人脸验证成功" if verified else "人脸验证失败",
    )
    return snapshot


@app.delete("/api/face/profile", response_model=dict)
async def face_delete_profile() -> dict:
    """删除已注册的人脸档案。"""
    _, adapter, _ = _face_engine()
    adapter.clear_profile()
    identity.reset()
    record_identity_event("identity.face_profile_deleted", "info", "人脸档案已删除")
    return {"ok": True}


@app.get("/api/reminders", response_model=list[ReminderRecord])
async def list_reminders(
    status: ReminderStatus | None = "pending",
    limit: int = 50,
    _: None = Depends(require_owner_identity),
) -> list[ReminderRecord]:
    return local_state.list_reminders(status=status, limit=limit)


@app.post("/api/reminders", response_model=ReminderRecord)
async def create_reminder(
    request: ReminderCreateRequest,
    _: None = Depends(require_owner_identity),
) -> ReminderRecord:
    return local_state.create_reminder(request)


@app.patch("/api/reminders/{reminder_id}", response_model=ReminderRecord)
async def update_reminder(
    reminder_id: str,
    request: ReminderUpdateRequest,
    _: None = Depends(require_owner_identity),
) -> ReminderRecord:
    reminder = local_state.update_reminder(reminder_id, request)
    if reminder is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "待处理提醒不存在"})
    return reminder


@app.delete("/api/reminders/{reminder_id}", response_model=ReminderDeleteResponse)
async def cancel_reminder(
    reminder_id: str,
    _: None = Depends(require_owner_identity),
) -> ReminderDeleteResponse:
    return ReminderDeleteResponse(deleted=local_state.cancel_reminder(reminder_id))


@app.get("/api/settings", response_model=DesktopSettings)
async def get_desktop_settings(_: None = Depends(require_owner_identity)) -> DesktopSettings:
    return local_state.get_settings()


@app.patch("/api/settings", response_model=DesktopSettings)
async def update_desktop_settings(
    request: DesktopSettingsUpdate,
    _: None = Depends(require_owner_identity),
) -> DesktopSettings:
    return local_state.update_settings(request)


@app.get("/api/system/logs", response_model=list[SystemLogRecord])
async def list_system_logs(
    limit: int = 50,
    _: None = Depends(require_owner_identity),
) -> list[SystemLogRecord]:
    return local_state.list_logs(limit=limit)


@app.get("/api/tools", response_model=list[ToolDefinition])
async def list_tools() -> list[ToolDefinition]:
    return tools.definitions()


@app.post("/api/tools/execute", response_model=ToolCallResult)
async def execute_tool(request: ToolExecuteRequest) -> ToolCallResult:
    try:
        if (
            request.tool_name == "open_file"
            and settings.langgraph_approval_interrupt_enabled
        ):
            return await tool_approval_workflow.start_open_file(request)
        return tools.execute(request, identity.snapshot())
    except ToolPolicyError as exc:
        raise tool_error_response(exc) from exc


@app.get("/api/tools/approvals", response_model=list[ToolApproval])
async def list_tool_approvals(
    status: str | None = "pending",
    limit: int = 50,
    _: None = Depends(require_owner_identity),
) -> list[ToolApproval]:
    return tools.list_approvals(status=status, limit=limit)


@app.post("/api/tools/approvals/{approval_id}/approve", response_model=ToolCallResult)
async def approve_tool(approval_id: str) -> ToolCallResult:
    try:
        approval = tools.get_approval(approval_id)
        if (
            approval.tool_name == "open_file"
            and settings.langgraph_approval_interrupt_enabled
        ):
            return await tool_approval_workflow.approve(approval_id)
        return tools.approve(approval_id, identity.snapshot())
    except ToolPolicyError as exc:
        raise tool_error_response(exc) from exc


@app.post("/api/tools/approvals/{approval_id}/reject", response_model=ToolCallResult)
async def reject_tool(approval_id: str) -> ToolCallResult:
    try:
        approval = tools.get_approval(approval_id)
        if (
            approval.tool_name == "open_file"
            and settings.langgraph_approval_interrupt_enabled
        ):
            return await tool_approval_workflow.reject(approval_id)
        return tools.reject(approval_id, identity.snapshot())
    except ToolPolicyError as exc:
        raise tool_error_response(exc) from exc


@app.get("/api/tools/audit", response_model=list[ToolAuditRecord])
async def list_tool_audit(
    limit: int = 100,
    _: None = Depends(require_owner_identity),
) -> list[ToolAuditRecord]:
    return tools.list_audit(limit=limit)


@app.get("/api/langgraph/checkpoints", response_model=CheckpointDatabaseSummary)
async def get_langgraph_checkpoints(
    include_runtime: bool = False,
    _: None = Depends(require_owner_identity),
) -> CheckpointDatabaseSummary:
    return await checkpoint_maintenance.summary(include_runtime=include_runtime)


@app.post(
    "/api/langgraph/checkpoints/cleanup",
    response_model=CheckpointCleanupResult,
)
async def cleanup_langgraph_checkpoints(
    request: CheckpointCleanupRequest,
    _: None = Depends(require_owner_identity),
) -> CheckpointCleanupResult:
    try:
        return await checkpoint_maintenance.cleanup(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CHECKPOINT_CLEANUP", "message": str(exc)},
        ) from exc


@app.post("/api/agent/chat", response_model=AgentResponse)
async def agent_chat(request: AgentRequest) -> AgentResponse:
    try:
        response = await agent.respond(request)
    except AgentProviderError as exc:
        raise agent_error_response(exc) from exc
    await pet_event_hub.broadcast(PetActionEvent(
        action_id=response.action_id,
        emotion=response.emotion,
        mouth_mode=response.mouth_mode,
        interruptible=True,
    ))
    return response


@app.websocket("/api/agent/events")
async def agent_events(websocket: WebSocket) -> None:
    """Handle one local Agent conversation stream per WebSocket connection."""
    await websocket.accept()
    try:
        while True:
            raw_message = await websocket.receive()
            if raw_message["type"] == "websocket.disconnect":
                break
            if raw_message.get("text") is None:
                if not await _try_send_agent_event(websocket, AgentErrorEvent(
                    code="INVALID_MESSAGE",
                    message="Agent 事件必须是 JSON 文本",
                ).model_dump()):
                    return
                continue

            request_id = ""
            session_id = ""
            try:
                payload = json.loads(raw_message["text"])
                if isinstance(payload, dict):
                    request_id = str(payload.get("request_id") or "")
                    session_id = str(payload.get("session_id") or "")
                event = AgentMessageEvent.model_validate(payload)
            except (json.JSONDecodeError, ValidationError):
                if not await _try_send_agent_event(websocket, AgentErrorEvent(
                    request_id=request_id,
                    session_id=session_id,
                    code="INVALID_MESSAGE",
                    message="Agent 事件格式无效",
                ).model_dump()):
                    return
                continue

            if not await _try_send_agent_event(websocket, AgentStatusEvent(
                request_id=event.request_id,
                session_id=event.session_id,
                status="thinking",
            ).model_dump()):
                return
            try:
                response = await agent.respond(event.agent_request())
                if not await _try_send_agent_event(websocket, AgentResponseEvent(
                    request_id=event.request_id,
                    session_id=event.session_id,
                    response=response,
                ).model_dump(mode="json")):
                    return
                action = PetActionEvent(
                    action_id=response.action_id,
                    emotion=response.emotion,
                    mouth_mode=response.mouth_mode,
                    interruptible=True,
                )
                action_payload = action.wire_payload()
                if not await _try_send_agent_event(websocket, AgentPetActionEvent(
                    request_id=event.request_id,
                    session_id=event.session_id,
                    action=action_payload,
                ).model_dump()):
                    return
                await pet_event_hub.broadcast(action)
                if not await _try_send_agent_event(websocket, AgentStatusEvent(
                    request_id=event.request_id,
                    session_id=event.session_id,
                    status="completed",
                ).model_dump()):
                    return
            except AgentProviderError as exc:
                if not await _try_send_agent_event(websocket, AgentErrorEvent(
                    request_id=event.request_id,
                    session_id=event.session_id,
                    code=exc.code,
                    message=str(exc),
                ).model_dump()):
                    return
            except Exception:
                if not await _try_send_agent_event(websocket, AgentErrorEvent(
                    request_id=event.request_id,
                    session_id=event.session_id,
                    code="AGENT_INTERNAL_ERROR",
                    message="文本 Agent 处理失败",
                ).model_dump()):
                    return
    except WebSocketDisconnect:
        pass


@app.delete("/api/agent/sessions/{session_id}", response_model=AgentSessionClearResponse)
async def clear_agent_session(session_id: str) -> AgentSessionClearResponse:
    normalized_session_id = session_id.strip()
    if not normalized_session_id or len(normalized_session_id) > 128:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_REQUEST", "message": "会话标识无效"},
        )
    return AgentSessionClearResponse(
        session_id=normalized_session_id,
        cleared=agent.clear_session(normalized_session_id),
    )


@app.get("/api/memories/candidates", response_model=list[MemoryCandidate])
async def list_memory_candidates(_: None = Depends(require_owner_identity)) -> list[MemoryCandidate]:
    return agent.memory_store.list_candidates()


@app.patch("/api/memories/candidates/{candidate_id}", response_model=MemoryCandidate)
async def update_memory_candidate(
    candidate_id: str,
    draft: MemoryDraft,
    _: None = Depends(require_owner_identity),
) -> MemoryCandidate:
    candidate = agent.memory_store.update_candidate(candidate_id, draft)
    if candidate is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "记忆候选不存在"})
    return candidate


@app.post("/api/memories/candidates/{candidate_id}/confirm", response_model=MemoryRecord)
async def confirm_memory_candidate(
    candidate_id: str,
    draft: MemoryDraft,
    _: None = Depends(require_owner_identity),
) -> MemoryRecord:
    memory = agent.memory_store.confirm_candidate(candidate_id, draft)
    if memory is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "记忆候选不存在"})
    return memory


@app.delete("/api/memories/candidates/{candidate_id}", response_model=MemoryDeleteResponse)
async def delete_memory_candidate(
    candidate_id: str,
    _: None = Depends(require_owner_identity),
) -> MemoryDeleteResponse:
    return MemoryDeleteResponse(deleted=agent.memory_store.delete_candidate(candidate_id))


@app.get("/api/memories", response_model=list[MemoryRecord])
async def list_memories(_: None = Depends(require_owner_identity)) -> list[MemoryRecord]:
    return agent.memory_store.list_memories()


@app.patch("/api/memories/{memory_id}", response_model=MemoryRecord)
async def update_memory(
    memory_id: str,
    draft: MemoryDraft,
    _: None = Depends(require_owner_identity),
) -> MemoryRecord:
    memory = agent.memory_store.update_memory(memory_id, draft)
    if memory is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "记忆不存在"})
    return memory


@app.delete("/api/memories/{memory_id}", response_model=MemoryDeleteResponse)
async def delete_memory(
    memory_id: str,
    _: None = Depends(require_owner_identity),
) -> MemoryDeleteResponse:
    return MemoryDeleteResponse(deleted=agent.memory_store.delete_memory(memory_id))


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "provider": settings.speech_provider,
        "model": settings.speech_model,
        "ttsConfigured": settings.tts_configured,
        "asrConfigured": settings.asr_configured,
        "doubaoAsrConfigured": settings.doubao_asr_configured,
        "agentProvider": settings.agent_provider,
        "agentModel": settings.agent_model,
        "agentConfigured": settings.agent_configured,
        "agentReady": settings.agent_ready,
        "agentRequireRemote": settings.agent_require_remote,
        "agentFallbackToMock": settings.agent_fallback_to_mock,
        "agentConfigurationIssues": list(settings.agent_configuration_issues),
        "identityStatus": identity.snapshot().status,
        "identityAdapter": identity.snapshot().adapter,
        "privateMemoryAvailable": identity.snapshot().can_read_private_memory,
        "voiceprintProvider": settings.voiceprint_provider,
        "voiceprintMaxAudioBytes": settings.voiceprint_max_audio_bytes,
        "voiceprintRtcConfigured": settings.voiceprint_rtc_configured,
        "voiceprintRtcCallbackConfigured": settings.voiceprint_rtc_callback_configured,
        "voiceprintRtcLiveConfigured": settings.voiceprint_rtc_live_configured,
        "voiceprintRtcOpenapiConfigured": settings.voiceprint_rtc_openapi_configured,
        "voiceprintRtcApiVersion": settings.voiceprint_rtc_api_version,
        "faceRecognitionEnabled": settings.face_recognition_enabled,
        "faceRecognitionConfigured": settings.face_recognition_enabled and _face_model_available(),
        "ragEmbeddingProvider": settings.rag_embedding_provider,
        "ragEmbeddingConfigured": settings.rag_embedding_configured,
    }


@app.get("/api/rag/health", response_model=RagHealthResponse)
async def rag_health() -> RagHealthResponse:
    return await rag.health()


@app.get("/api/rag/documents/{collection}", response_model=list[RagIngestResponse])
async def list_rag_documents(collection: str) -> list[RagIngestResponse]:
    try:
        return await rag.list_documents(collection)
    except (RagError, ValueError) as exc:
        status_code = exc.status_code if isinstance(exc, RagError) else 422
        code = exc.code if isinstance(exc, RagError) else "INVALID_REQUEST"
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": str(exc)},
        ) from exc


@app.post("/api/rag/documents", response_model=RagIngestResponse)
async def ingest_rag_document(
    collection: Annotated[str, Form(...)],
    document: Annotated[UploadFile, File(...)],
    source_label: Annotated[str | None, Form()] = None,
) -> RagIngestResponse:
    content = await document.read(settings.rag_max_upload_bytes + 1)
    try:
        return await rag.ingest(
            collection=collection,
            filename=document.filename or "document.txt",
            content_type=document.content_type,
            content=content,
            source_label=source_label,
        )
    except (RagError, ValueError) as exc:
        status_code = exc.status_code if isinstance(exc, RagError) else 422
        code = exc.code if isinstance(exc, RagError) else "INVALID_REQUEST"
        raise HTTPException(status_code=status_code, detail={"code": code, "message": str(exc)}) from exc


@app.post("/api/rag/search", response_model=RagSearchResponse)
async def search_rag(request: RagSearchRequest) -> RagSearchResponse:
    try:
        return await rag.search(request)
    except RagError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@app.delete("/api/rag/documents/{collection}/{document_id}", response_model=RagDeleteResponse)
async def delete_rag_document(collection: str, document_id: str) -> RagDeleteResponse:
    try:
        return await rag.delete(collection, document_id)
    except (RagError, ValueError) as exc:
        status_code = exc.status_code if isinstance(exc, RagError) else 422
        code = exc.code if isinstance(exc, RagError) else "INVALID_REQUEST"
        raise HTTPException(status_code=status_code, detail={"code": code, "message": str(exc)}) from exc


@app.get("/api/personas", response_model=list[PersonaProfile])
async def list_personas() -> list[PersonaProfile]:
    return persona_store.list_profiles()


@app.get("/api/personas/active")
async def get_active_persona() -> PersonaProfile | None:
    return persona_store.get_active()


@app.post("/api/personas", response_model=PersonaProfile)
async def create_persona(draft: PersonaProfileDraft) -> PersonaProfile:
    return persona_store.create_profile(draft)


@app.post("/api/personas/deactivate")
async def deactivate_personas() -> dict[str, bool]:
    persona_store.deactivate_all()
    agent.reset_conversation_contexts()
    return {"ok": True}


@app.get("/api/personas/{profile_id}", response_model=PersonaProfile)
async def get_persona(profile_id: str) -> PersonaProfile:
    profile = persona_store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "人格配置不存在"},
        )
    if profile.is_active:
        agent.reset_conversation_contexts()
    return profile


@app.patch("/api/personas/{profile_id}", response_model=PersonaProfile)
async def update_persona(profile_id: str, draft: PersonaProfileDraft) -> PersonaProfile:
    profile = persona_store.update_profile(profile_id, draft)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "人格配置不存在"},
        )
    if profile.is_active:
        agent.reset_conversation_contexts()
    return profile


@app.delete("/api/personas/{profile_id}")
async def delete_persona(profile_id: str) -> dict[str, bool]:
    profile = persona_store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "人格配置不存在"},
        )
    deleted = persona_store.delete_profile(profile_id)
    if profile.is_active and deleted:
        agent.reset_conversation_contexts()
    return {"ok": True}


@app.post("/api/personas/{profile_id}/activate", response_model=PersonaProfile)
async def activate_persona(profile_id: str) -> PersonaProfile:
    profile = persona_store.activate(profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "人格配置不存在"},
        )
    agent.reset_conversation_contexts()
    return profile


@app.get(
    "/api/personas/{profile_id}/versions",
    response_model=list[PersonaProfileVersion],
)
async def list_persona_versions(profile_id: str) -> list[PersonaProfileVersion]:
    if persona_store.get_profile(profile_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "人格配置不存在"},
        )
    return persona_store.list_versions(profile_id)


@app.post("/api/personas/{profile_id}/rollback", response_model=PersonaProfile)
async def rollback_persona(profile_id: str, payload: dict[str, Any]) -> PersonaProfile:
    version_id = str(payload.get("version_id", "")).strip()
    if not version_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_REQUEST", "message": "缺少版本标识"},
        )
    profile = persona_store.rollback(profile_id, version_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "配置或版本不存在"},
        )
    if profile.is_active:
        agent.reset_conversation_contexts()
    return profile


@app.post("/api/pet/events")
async def publish_pet_event(event: PetActionEvent) -> dict[str, object]:
    delivered = await pet_event_hub.broadcast(event)
    return {"ok": True, "delivered": delivered, "event": event.wire_payload()}


@app.websocket("/api/pet/events")
async def pet_events(websocket: WebSocket) -> None:
    await pet_event_hub.connect(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await pet_event_hub.disconnect(websocket)


@app.post("/api/speech/tts", response_model=TtsResponse)
async def text_to_speech(request: TtsRequest) -> TtsResponse:
    try:
        result = await provider.synthesize(TtsInput(
            text=request.text,
            language=request.language,
            voice_id=request.voice_id,
            emotion=request.emotion,
            speed=request.speed,
            pitch=request.pitch,
            vol=request.vol,
        ))
    except SpeechProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return TtsResponse(**result)


@app.post("/api/speech/asr", response_model=AsrResponse)
async def speech_to_text(
    audio: Annotated[UploadFile, File(...)],
    language: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
) -> AsrResponse:
    del model
    content = await audio.read()
    try:
        result = await provider.transcribe(AsrInput(
            audio=content,
            filename=audio.filename or "speech.webm",
            content_type=audio.content_type or "application/octet-stream",
            language=language,
        ))
    except SpeechProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return AsrResponse(**result)


async def _send_ws_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


@app.websocket("/api/speech/asr/stream")
async def speech_to_text_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    asr = DoubaoSaucAsr(settings)
    reader_task: asyncio.Task[None] | None = None
    started = False

    async def relay_responses() -> None:
        try:
            async for response in asr.responses():
                if response.text is not None:
                    await _send_ws_json(websocket, {
                        "type": "final" if response.is_last else "partial",
                        "text": response.text,
                        "language": None,
                        "traceId": response.log_id,
                    })
        except SpeechProviderError as exc:
            await _send_ws_json(websocket, {
                "type": "error",
                "code": exc.code,
                "message": str(exc),
            })
        finally:
            await _send_ws_json(websocket, {"type": "closed"})

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                if not started:
                    await _send_ws_json(websocket, {
                        "type": "error",
                        "code": "INVALID_STATE",
                        "message": "请先发送 start 消息",
                    })
                    continue
                await asr.send_audio(message["bytes"])
                continue

            text = message.get("text")
            if not text:
                continue
            try:
                command = json.loads(text)
            except json.JSONDecodeError:
                await _send_ws_json(websocket, {
                    "type": "error",
                    "code": "INVALID_REQUEST",
                    "message": "控制消息必须是 JSON",
                })
                continue

            command_type = command.get("type")
            if command_type == "start":
                if started:
                    await _send_ws_json(websocket, {
                        "type": "error",
                        "code": "INVALID_STATE",
                        "message": "当前语音流已经启动",
                    })
                    continue
                language = command.get("language")
                await asr.start(language if isinstance(language, str) else None)
                started = True
                reader_task = asyncio.create_task(relay_responses())
                await _send_ws_json(websocket, {"type": "ready"})
            elif command_type == "stop":
                if not started:
                    await _send_ws_json(websocket, {
                        "type": "error",
                        "code": "INVALID_STATE",
                        "message": "当前语音流尚未启动",
                    })
                    continue
                await asr.send_audio(b"", is_last=True)
                if reader_task is not None:
                    await reader_task
                break
            else:
                await _send_ws_json(websocket, {
                    "type": "error",
                    "code": "INVALID_REQUEST",
                    "message": "仅支持 start、stop 控制消息",
                })
    except WebSocketDisconnect:
        pass
    except SpeechProviderError as exc:
        try:
            await _send_ws_json(websocket, {
                "type": "error",
                "code": exc.code,
                "message": str(exc),
            })
        except RuntimeError:
            pass
    finally:
        if reader_task is not None and not reader_task.done():
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)
        await asr.close()
