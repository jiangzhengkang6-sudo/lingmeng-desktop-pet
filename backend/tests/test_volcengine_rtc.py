from dataclasses import replace
from datetime import UTC, datetime
import base64
import json
import struct
import time

import httpx
import pytest

from backend.app.config import DEFAULT_VOICEPRINT_RTC_API_VERSION, Settings
from backend.app.volcengine_rtc import (
    RTC_VOICEPRINT_ENROLLMENT_API_VERSION,
    RtcOpenApiError,
    RtcSessionContextError,
    RtcVoiceChatSession,
    RtcClientJoinToken,
    RtcSceneStore,
    RtcVoiceChatStartRequest,
    RtcVoiceprintBridge,
    VolcengineRtcOpenApiClient,
    _create_rtc_access_token,
)


def rtc_settings(tmp_path) -> Settings:
    return replace(
        Settings.from_environment(),
        voiceprint_provider="volcengine-rtc",
        voiceprint_rtc_owner_name="desktop-owner",
        voiceprint_rtc_score_threshold=50,
        voiceprint_rtc_bridge_secret="bridge-secret",
        voiceprint_rtc_access_key_id="test-access-key",
        voiceprint_rtc_secret_access_key="test-secret-key",
        voiceprint_rtc_app_id="012345678901234567890123",
        voiceprint_rtc_api_version=DEFAULT_VOICEPRINT_RTC_API_VERSION,
        voiceprint_rtc_scene_path=tmp_path / "voiceprint-rtc-scene.json",
    )


@pytest.mark.asyncio
async def test_openapi_client_signs_and_starts_voice_chat(tmp_path) -> None:
    settings = replace(
        rtc_settings(tmp_path),
        voiceprint_rtc_callback_url="",
        voiceprint_rtc_callback_secret="",
    )
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "ResponseMetadata": {"RequestId": "request-1"},
            "Result": {"TaskId": "task-1", "AppId": "012345678901234567890123", "RoomId": "room-1"},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        openapi = VolcengineRtcOpenApiClient(
            settings,
            client=client,
            now=lambda: datetime(2026, 9, 9, 8, 30, tzinfo=UTC),
        )
        response = await openapi.start_voice_chat({"AppId": "012345678901234567890123", "RoomId": "room-1"})
    finally:
        await client.aclose()

    assert response["Result"]["TaskId"] == "task-1"
    request = requests[0]
    assert request.url.params["Action"] == "StartVoiceChat"
    assert request.url.params["Version"] == "2025-06-01"
    assert json.loads(request.content) == {"AppId": "012345678901234567890123", "RoomId": "room-1"}
    assert request.headers["X-Date"] == "20260909T083000Z"
    assert request.headers["X-Content-Sha256"]
    assert "Credential=test-access-key/20260909/cn-north-1/rtc/request" in request.headers["Authorization"]
    assert "test-secret-key" not in request.headers["Authorization"]


@pytest.mark.asyncio
async def test_openapi_client_stops_voice_chat_with_its_room_id(tmp_path) -> None:
    settings = rtc_settings(tmp_path)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "ResponseMetadata": {"RequestId": "request-2"},
            "Result": {"TaskId": "task-1", "AppId": "012345678901234567890123", "RoomId": "room-1"},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        openapi = VolcengineRtcOpenApiClient(settings, client=client)
        response = await openapi.stop_voice_chat("task-1", "room-1")
    finally:
        await client.aclose()

    assert response["Result"]["TaskId"] == "task-1"
    request = requests[0]
    assert request.url.params["Action"] == "StopVoiceChat"
    assert json.loads(request.content) == {
        "AppId": "012345678901234567890123",
        "RoomId": "room-1",
        "TaskId": "task-1",
    }


@pytest.mark.asyncio
async def test_openapi_client_registers_voiceprint_with_its_required_api_version(tmp_path) -> None:
    settings = rtc_settings(tmp_path)
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"Result": "voiceprint-123"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        openapi = VolcengineRtcOpenApiClient(settings, client=client)
        response = await openapi.register_voiceprint({"AppId": "012345678901234567890123", "Audio": "base64-audio"})
    finally:
        await client.aclose()

    assert response["Result"] == "voiceprint-123"
    assert requests[0].url.params["Action"] == "RegisterVoicePrint"
    assert requests[0].url.params["Version"] == RTC_VOICEPRINT_ENROLLMENT_API_VERSION


def test_scene_rejects_runtime_field_overrides(tmp_path) -> None:
    path = tmp_path / "voiceprint-rtc-scene.json"
    path.write_text('{"AppId":"must-not-be-here","Config":{}}', encoding="utf-8")

    with pytest.raises(RtcOpenApiError) as exc_info:
        RtcSceneStore(path).load()

    assert exc_info.value.code == "RTC_SCENE_INVALID"


def test_scene_writes_pre_registered_voiceprint_configuration(tmp_path) -> None:
    path = tmp_path / "voiceprint-rtc-scene.json"
    path.write_text(json.dumps({
        "Config": {"ASRConfig": {"ProviderParams": {"StreamMode": 1}}},
    }), encoding="utf-8")

    RtcSceneStore(path).configure_voiceprint_recognition("voiceprint-123", 50.0)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "AgentConfig": {
            "VoicePrint": {"Mode": 2, "IdList": ["voiceprint-123"], "Score": 50},
            "EnableConversationStateCallback": True,
        },
        "Config": {
            "ASRConfig": {"ProviderParams": {"StreamMode": 0}},
            "SubtitleConfig": {"SubtitleMode": 0},
        },
    }


def test_scene_load_normalizes_integral_float_voiceprint_score_for_rtc(tmp_path) -> None:
    path = tmp_path / "voiceprint-rtc-scene.json"
    path.write_text(json.dumps({
        "AgentConfig": {
            "VoicePrint": {"Mode": 2, "IdList": ["voiceprint-123"], "Score": 50.0},
        },
        "Config": {},
    }), encoding="utf-8")

    scene = RtcSceneStore(path).load()

    assert scene["AgentConfig"]["VoicePrint"]["Score"] == 50
    assert isinstance(scene["AgentConfig"]["VoicePrint"]["Score"], int)


def test_scene_rejects_fractional_voiceprint_score_for_rtc(tmp_path) -> None:
    path = tmp_path / "voiceprint-rtc-scene.json"
    path.write_text(json.dumps({
        "AgentConfig": {
            "VoicePrint": {"Mode": 2, "IdList": ["voiceprint-123"], "Score": 50.5},
        },
        "Config": {},
    }), encoding="utf-8")

    with pytest.raises(RtcOpenApiError) as exc_info:
        RtcSceneStore(path).load()

    assert exc_info.value.code == "RTC_SCENE_INVALID"


def test_start_request_rejects_client_supplied_task_id() -> None:
    with pytest.raises(ValueError, match="taskId"):
        RtcVoiceChatStartRequest.model_validate({
            "roomId": "room-1",
            "agentUserId": "pet-agent",
            "targetUserIds": ["desktop-owner"],
            "taskId": "client-controlled-task",
            "confirmed": True,
        })


@pytest.mark.asyncio
async def test_bridge_enrollment_writes_returned_voiceprint_to_scene(tmp_path) -> None:
    settings = rtc_settings(tmp_path)

    class FakeOpenApiClient:
        async def register_voiceprint(self, payload):
            assert payload["AppId"] == "012345678901234567890123"
            assert payload["AudioName"] == "desktop-owner"
            assert payload["AudioFormat"] == 0
            assert payload["Version"] == 2
            assert payload["Audio"]
            return {
                "ResponseMetadata": {"RequestId": "request-1"},
                "Result": "voiceprint-123",
            }

        async def close(self):
            return None

    bridge = RtcVoiceprintBridge(settings, client=FakeOpenApiClient())
    enrollment = await bridge.enroll_owner_voiceprint(b"example-pcm-wav")

    assert enrollment.model_dump(by_alias=True) == {
        "voiceprintId": "voiceprint-123",
        "audioName": "desktop-owner",
        "algorithmVersion": 2,
        "sceneUpdated": True,
        "requestId": "request-1",
    }
    scene = json.loads(settings.voiceprint_rtc_scene_path.read_text(encoding="utf-8"))
    assert scene["AgentConfig"]["VoicePrint"]["IdList"] == ["voiceprint-123"]


@pytest.mark.asyncio
async def test_bridge_merges_scene_with_server_owned_runtime_values(tmp_path) -> None:
    settings = replace(
        rtc_settings(tmp_path),
        voiceprint_rtc_callback_url="",
        voiceprint_rtc_callback_secret="",
    )
    settings.voiceprint_rtc_scene_path.write_text(json.dumps({
        "AgentConfig": {"WelcomeMessage": "你好"},
        "Config": {"ProviderManaged": {"VoicePrint": {"Mode": 2}}},
    }), encoding="utf-8")

    class FakeOpenApiClient:
        async def start_voice_chat(self, payload):
            assert payload["AppId"] == "012345678901234567890123"
            assert payload["RoomId"] == "room-1"
            assert payload["TaskId"].startswith("desktoppet")
            assert len(payload["TaskId"]) == len("desktoppet") + 32
            assert payload["AgentConfig"] == {
                "WelcomeMessage": "你好",
                "UserId": "pet-agent",
                "TargetUserId": ["desktop-owner"],
                "EnableConversationStateCallback": True,
            }
            assert payload["Config"] == {
                "ProviderManaged": {"VoicePrint": {"Mode": 2}},
                "SubtitleConfig": {"SubtitleMode": 0},
            }
            return {
                "ResponseMetadata": {"RequestId": "request-1"},
                "Result": {
                    "TaskId": payload["TaskId"],
                    "AppId": "012345678901234567890123",
                    "RoomId": "room-1",
                },
            }

        async def stop_voice_chat(self, task_id, room_id):
            assert room_id == "room-1"
            return {
                "Result": {
                    "TaskId": task_id,
                    "AppId": "012345678901234567890123",
                    "RoomId": room_id,
                },
            }

        async def close(self):
            return None

    bridge = RtcVoiceprintBridge(settings, client=FakeOpenApiClient())
    session = await bridge.start_session(RtcVoiceChatStartRequest(
        roomId="room-1",
        agentUserId="pet-agent",
        targetUserIds=["desktop-owner"],
        confirmed=True,
    ))

    assert session.task_id.startswith("desktoppet")
    assert session.app_id == "012345678901234567890123"
    assert session.room_id == "room-1"
    assert session.request_id == "request-1"
    assert bridge.require_active_session(session.task_id) == session

    stopped = await bridge.stop_session(session.task_id)
    assert stopped.task_id == session.task_id
    with pytest.raises(RtcSessionContextError, match="不是当前有效会话"):
        bridge.require_active_session(session.task_id)


@pytest.mark.asyncio
async def test_bridge_injects_rts_callback_configuration_when_live_ready(tmp_path) -> None:
    settings = replace(
        rtc_settings(tmp_path),
        voiceprint_rtc_callback_url="https://rtc-tunnel.example.test/api/identity/rtc/rts/messages",
        voiceprint_rtc_callback_secret="rts-shared-secret",
    )
    settings.voiceprint_rtc_scene_path.write_text(json.dumps({
        "Config": {"ASRConfig": {"ProviderParams": {"StreamMode": 0}}},
    }), encoding="utf-8")

    class FakeOpenApiClient:
        async def start_voice_chat(self, payload):
            assert payload["AgentConfig"]["ServerMessageURLForRTS"] == settings.voiceprint_rtc_callback_url
            assert payload["AgentConfig"]["ServerMessageSignatureForRTS"] == "rts-shared-secret"
            assert payload["Config"]["SubtitleConfig"] == {"SubtitleMode": 0}
            return {"Result": {"TaskId": payload["TaskId"], "RoomId": "room-1"}}

        async def close(self):
            return None

    bridge = RtcVoiceprintBridge(settings, client=FakeOpenApiClient())
    request = RtcVoiceChatStartRequest(
        roomId="room-1",
        agentUserId="pet-agent",
        targetUserIds=["desktop-owner"],
        confirmed=True,
    )
    await bridge.start_session(request)
    session, target_user_ids = bridge.require_single_active_session()
    assert session.task_id.startswith("desktoppet")
    assert target_user_ids == ("desktop-owner",)


def test_bridge_expires_active_sessions(tmp_path) -> None:
    settings = replace(rtc_settings(tmp_path), voiceprint_rtc_session_ttl_seconds=10)
    now = [100.0]
    bridge = RtcVoiceprintBridge(settings, clock=lambda: now[0])
    session = RtcVoiceChatSession(taskId="task-expiring", appId="012345678901234567890123")

    bridge.register_active_session(session)
    assert bridge.require_active_session("task-expiring") == session

    now[0] = 110.0
    with pytest.raises(RtcSessionContextError, match="过期"):
        bridge.require_active_session("task-expiring")


def test_bridge_status_reports_selected_api_version_without_credentials(tmp_path) -> None:
    status = RtcVoiceprintBridge(rtc_settings(tmp_path)).status()

    assert status.api_version == "2025-06-01"
    assert status.uses_current_api_version is True
    assert "test-secret-key" not in status.model_dump_json()


@pytest.mark.asyncio
async def test_bridge_creates_short_lived_official_rtc_client_token(tmp_path) -> None:
    settings = replace(rtc_settings(tmp_path), voiceprint_rtc_app_key="test-app-key")
    bridge = RtcVoiceprintBridge(settings)
    bridge.register_active_session(
        RtcVoiceChatSession(taskId="task-1", appId="012345678901234567890123", roomId="room-1"),
        ["desktop-owner"],
    )

    token = await bridge.create_client_join_token(
        task_id="task-1",
        user_id="desktop-owner",
        ttl_seconds=900,
    )

    assert isinstance(token, RtcClientJoinToken)
    assert token.app_id == "012345678901234567890123"
    assert token.room_id == "room-1"
    assert token.user_id == "desktop-owner"
    assert token.token.startswith("001012345678901234567890123")
    assert "test-app-key" not in token.token
    assert token.expires_at_ms > int(time.time() * 1000)


@pytest.mark.asyncio
async def test_bridge_rejects_client_token_for_non_target_user(tmp_path) -> None:
    settings = replace(rtc_settings(tmp_path), voiceprint_rtc_app_key="test-app-key")
    bridge = RtcVoiceprintBridge(settings)
    bridge.register_active_session(
        RtcVoiceChatSession(taskId="task-1", appId="012345678901234567890123", roomId="room-1"),
        ["desktop-owner"],
    )

    with pytest.raises(RtcOpenApiError) as exc_info:
        await bridge.create_client_join_token(
            task_id="task-1",
            user_id="unexpected-user",
        )

    assert exc_info.value.code == "RTC_CLIENT_USER_NOT_ALLOWED"


def _decode_rtc_token_payload(token: str) -> tuple[str, dict[int, int], int]:
    assert token.startswith("001")
    app_id = token[3:27]
    encoded = token[27:]
    raw = base64.b64decode(encoded)

    def read_bytes(buffer: bytes, offset: int) -> tuple[bytes, int]:
        length = struct.unpack_from("<H", buffer, offset)[0]
        start = offset + 2
        return buffer[start:start + length], start + length

    message, offset = read_bytes(raw, 0)
    signature, offset = read_bytes(raw, offset)
    assert signature
    message_offset = 0
    _nonce = struct.unpack_from("<I", message, message_offset)[0]
    message_offset += 4
    _issued_at = struct.unpack_from("<I", message, message_offset)[0]
    message_offset += 4
    expire_at = struct.unpack_from("<I", message, message_offset)[0]
    message_offset += 4
    _room_id, message_offset = read_bytes(message, message_offset)
    _user_id, message_offset = read_bytes(message, message_offset)
    count = struct.unpack_from("<H", message, message_offset)[0]
    message_offset += 2
    privileges = {}
    for _ in range(count):
        privilege = struct.unpack_from("<H", message, message_offset)[0]
        message_offset += 2
        privileges[privilege] = struct.unpack_from("<I", message, message_offset)[0]
        message_offset += 4
    return app_id, privileges, expire_at


def test_rtc_access_token_uses_global_expiry_and_unlimited_privileges() -> None:
    expire_at = 1_800_000_000

    token = _create_rtc_access_token(
        app_id="012345678901234567890123",
        app_key="test-app-key",
        room_id="room-1",
        user_id="desktop-owner",
        expire_at=expire_at,
    )

    app_id, privileges, global_expire_at = _decode_rtc_token_payload(token)

    assert app_id == "012345678901234567890123"
    assert global_expire_at == expire_at
    assert privileges == {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}


def test_rtc_access_token_rejects_app_id_with_wrong_length() -> None:
    with pytest.raises(RtcOpenApiError, match="AppId"):
        _create_rtc_access_token(
            app_id="short-app-id",
            app_key="test-app-key",
            room_id="room-1",
            user_id="desktop-owner",
            expire_at=1_800_000_000,
        )
