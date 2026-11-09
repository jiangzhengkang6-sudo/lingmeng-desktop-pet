import base64
import hashlib
import hmac
import io
import json
import time
from unittest.mock import AsyncMock
import wave

import pytest
from dataclasses import replace
from fastapi.testclient import TestClient
from fastapi import WebSocketDisconnect

from backend.app import main
from backend.app.agent_workflow.approval_graph import ToolApprovalWorkflow
from backend.app.agent import AgentProviderError, AgentService
from backend.app.checkpoint_maintenance import (
    CheckpointCleanupResult,
    CheckpointDatabaseSummary,
)
from backend.app.controlled_tools import ControlledToolService
from backend.app.local_state import LocalStateStore
from backend.app.main import app
from backend.app.memory import MemoryStore, MemorySuggestion
from backend.app.rag import HashEmbeddingAdapter, InMemoryRagStore, RagService
from backend.app.rtc_rts import encode_rts_binary
from backend.app.identity import IdentityService, MockVoiceprintAdapter, VolcengineRtcVoiceprintAdapter
from backend.app.volcengine_rtc import (
    RtcVoiceChatSession,
    RtcVoiceprintBridge,
    RtcVoiceprintEnrollment,
)


def pcm_wav(seconds: int = 15) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\x00\x00" * 16_000 * seconds)
    return output.getvalue()


def test_health_exposes_safe_configuration_state() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "apiKey" not in body
    assert body["model"] == "speech-2.8-hd"
    assert "doubaoAsrConfigured" in body
    assert body["agentProvider"] in {"mock", "qwen", "openai-compatible"}
    assert "agentConfigured" in body
    assert isinstance(body["agentReady"], bool)
    assert isinstance(body["agentRequireRemote"], bool)
    assert isinstance(body["agentConfigurationIssues"], list)
    assert body["ragEmbeddingProvider"] in {"hash", "openai-compatible"}
    assert "ragEmbeddingConfigured" in body
    assert isinstance(body["voiceprintProvider"], str)
    assert isinstance(body["voiceprintMaxAudioBytes"], int)
    assert isinstance(body["voiceprintRtcConfigured"], bool)
    assert isinstance(body["voiceprintRtcOpenapiConfigured"], bool)
    assert isinstance(body["voiceprintRtcApiVersion"], str)


def test_real_voiceprint_route_is_closed_until_a_provider_is_integrated() -> None:
    response = TestClient(app).post(
        "/api/identity/verify",
        files={"audio": ("voice.webm", b"not-a-real-voice-sample", "audio/webm")},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "VOICEPRINT_NOT_CONFIGURED"


def test_rtc_voiceprint_observation_requires_signed_current_event(monkeypatch) -> None:
    test_settings = replace(
        main.settings,
        voiceprint_provider="volcengine-rtc",
        voiceprint_rtc_owner_name="desktop-owner",
        voiceprint_rtc_score_threshold=50,
        voiceprint_rtc_bridge_secret="test-bridge-secret",
        voiceprint_rtc_clock_skew_seconds=300,
    )
    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(
        main,
        "identity",
        IdentityService(VolcengineRtcVoiceprintAdapter("desktop-owner", 50)),
    )
    bridge = RtcVoiceprintBridge(test_settings)
    bridge.register_active_session(RtcVoiceChatSession(taskId="rtc-task"))
    monkeypatch.setattr(main, "rtc_voiceprint_bridge", bridge)
    body = b'{"task_id":"rtc-task","voiceprint_name":"desktop-owner","voiceprint_score":52}'
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"test-bridge-secret",
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        unsigned = client.post(
            "/api/identity/rtc/voiceprint-observations",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        signed = client.post(
            "/api/identity/rtc/voiceprint-observations",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Desktop-Pet-Voiceprint-Timestamp": timestamp,
                "X-Desktop-Pet-Voiceprint-Signature": signature,
            },
        )
        repeated = client.post(
            "/api/identity/rtc/voiceprint-observations",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Desktop-Pet-Voiceprint-Timestamp": timestamp,
                "X-Desktop-Pet-Voiceprint-Signature": signature,
            },
        )

    assert unsigned.status_code == 401
    assert unsigned.json()["detail"]["code"] == "VOICEPRINT_BRIDGE_UNAUTHORIZED"
    assert signed.status_code == 200
    assert signed.json()["status"] == "owner_verified"

    assert repeated.status_code == 200
    assert repeated.json()["status"] == "owner_verified"


def test_rtc_voiceprint_observation_rejects_stopped_or_unknown_task(monkeypatch) -> None:
    test_settings = replace(
        main.settings,
        voiceprint_provider="volcengine-rtc",
        voiceprint_rtc_owner_name="desktop-owner",
        voiceprint_rtc_score_threshold=50,
        voiceprint_rtc_bridge_secret="test-bridge-secret",
        voiceprint_rtc_clock_skew_seconds=300,
    )
    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(
        main,
        "identity",
        IdentityService(VolcengineRtcVoiceprintAdapter("desktop-owner", 50)),
    )
    bridge = RtcVoiceprintBridge(test_settings)
    monkeypatch.setattr(main, "rtc_voiceprint_bridge", bridge)
    body = b'{"task_id":"old-task","voiceprint_name":"desktop-owner","voiceprint_score":99}'
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"test-bridge-secret",
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    response = TestClient(app).post(
        "/api/identity/rtc/voiceprint-observations",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Desktop-Pet-Voiceprint-Timestamp": timestamp,
            "X-Desktop-Pet-Voiceprint-Signature": signature,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RTC_SESSION_NOT_ACTIVE"


def test_rtc_voiceprint_observation_cannot_replay_low_score_with_high_score(monkeypatch) -> None:
    test_settings = replace(
        main.settings,
        voiceprint_provider="volcengine-rtc",
        voiceprint_rtc_owner_name="desktop-owner",
        voiceprint_rtc_score_threshold=50,
        voiceprint_rtc_bridge_secret="test-bridge-secret",
        voiceprint_rtc_clock_skew_seconds=300,
    )
    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(
        main,
        "identity",
        IdentityService(VolcengineRtcVoiceprintAdapter("desktop-owner", 50)),
    )
    bridge = RtcVoiceprintBridge(test_settings)
    bridge.register_active_session(RtcVoiceChatSession(taskId="replay-task"))
    monkeypatch.setattr(main, "rtc_voiceprint_bridge", bridge)

    def signed_request(client, body: bytes):
        timestamp = str(int(time.time()))
        signature = hmac.new(
            b"test-bridge-secret",
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        return client.post(
            "/api/identity/rtc/voiceprint-observations",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Desktop-Pet-Voiceprint-Timestamp": timestamp,
                "X-Desktop-Pet-Voiceprint-Signature": signature,
            },
        )

    with TestClient(app) as client:
        low = signed_request(
            client,
            b'{"task_id":"replay-task","voiceprint_name":"desktop-owner","voiceprint_score":49}',
        )
        high = signed_request(
            client,
            b'{"task_id":"replay-task","voiceprint_name":"desktop-owner","voiceprint_score":99}',
        )

    assert low.status_code == 200
    assert low.json()["status"] == "guest"
    assert high.status_code == 200
    assert high.json()["status"] == "guest"


def test_starting_rtc_session_clears_previous_owner_state(monkeypatch) -> None:
    test_settings = replace(
        main.settings,
        voiceprint_provider="volcengine-rtc",
        voiceprint_rtc_owner_name="desktop-owner",
        voiceprint_rtc_score_threshold=50,
        voiceprint_rtc_bridge_secret="test-bridge-secret",
        voiceprint_rtc_access_key_id="test-access-key",
        voiceprint_rtc_secret_access_key="test-secret-key",
        voiceprint_rtc_app_id="test-app-id",
    )
    identity_service = IdentityService(MockVoiceprintAdapter())
    monkeypatch.setattr(main, "identity", identity_service)
    identity_service.apply_verification(True)
    bridge = RtcVoiceprintBridge(test_settings)
    bridge.start_session = AsyncMock(return_value=RtcVoiceChatSession(taskId="new-task"))
    monkeypatch.setattr(main, "rtc_voiceprint_bridge", bridge)

    with TestClient(app) as client:
        response = client.post("/api/identity/rtc/sessions", json={
            "roomId": "room-1",
            "agentUserId": "pet-agent",
            "targetUserIds": ["desktop-owner"],
            "confirmed": True,
        })

    assert response.status_code == 200
    assert identity_service.snapshot().status == "unknown"


def test_rtc_voiceprint_enrollment_requires_confirmation_and_valid_wav(monkeypatch) -> None:
    enrollment = AsyncMock(return_value=RtcVoiceprintEnrollment(
        voiceprintId="voiceprint-123",
        audioName="desktop-owner",
        algorithmVersion=2,
        sceneUpdated=True,
        requestId="request-1",
    ))
    monkeypatch.setattr(main.rtc_voiceprint_bridge, "enroll_owner_voiceprint", enrollment)
    valid_wav = pcm_wav()

    with TestClient(app) as client:
        unconfirmed = client.post(
            "/api/identity/rtc/voiceprints/register",
            data={"confirmed": "false"},
            files={"audio": ("owner.wav", valid_wav, "audio/wav")},
        )
        invalid = client.post(
            "/api/identity/rtc/voiceprints/register",
            data={"confirmed": "true"},
            files={"audio": ("owner.wav", b"not-a-wav", "audio/wav")},
        )
        registered = client.post(
            "/api/identity/rtc/voiceprints/register",
            data={"confirmed": "true"},
            files={"audio": ("owner.wav", valid_wav, "audio/wav")},
        )

    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["detail"]["code"] == "CONFIRMATION_REQUIRED"
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "INVALID_WAV"
    assert registered.status_code == 200
    assert registered.json()["voiceprintId"] == "voiceprint-123"
    enrollment.assert_awaited_once_with(valid_wav)


def test_rtc_session_start_requires_explicit_confirmation_and_server_configuration(monkeypatch) -> None:
    unconfigured_settings = replace(
        main.settings,
        voiceprint_provider="mock",
        voiceprint_rtc_owner_name="",
        voiceprint_rtc_score_threshold=None,
        voiceprint_rtc_bridge_secret="",
        voiceprint_rtc_access_key_id="",
        voiceprint_rtc_secret_access_key="",
        voiceprint_rtc_app_id="",
    )
    monkeypatch.setattr(main, "rtc_voiceprint_bridge", RtcVoiceprintBridge(unconfigured_settings))
    main.identity.reset()

    with TestClient(app) as client:
        unconfirmed = client.post("/api/identity/rtc/sessions", json={
            "roomId": "room-1",
            "agentUserId": "pet-agent",
            "targetUserIds": ["desktop-owner"],
        })
        unavailable = client.post("/api/identity/rtc/sessions", json={
            "roomId": "room-1",
            "agentUserId": "pet-agent",
            "targetUserIds": ["desktop-owner"],
            "confirmed": True,
        })

    assert unconfirmed.status_code == 422
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "RTC_OPENAPI_NOT_CONFIGURED"


def test_tts_without_key_returns_explainable_error(monkeypatch) -> None:
    monkeypatch.setattr(main.provider, "settings", replace(main.provider.settings, speech_api_key=""))
    response = TestClient(app).post("/api/speech/tts", json={"text": "hello"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "NOT_CONFIGURED"


def test_tts_route_returns_provider_hex_audio(monkeypatch) -> None:
    monkeypatch.setattr(main.provider, "synthesize", AsyncMock(return_value={
        "audioHex": "6869",
        "mimeType": "audio/mpeg",
        "traceId": "trace-1",
    }))

    response = TestClient(app).post("/api/speech/tts", json={"text": "hello"})

    assert response.status_code == 200
    assert response.json() == {
        "audioHex": "6869",
        "mimeType": "audio/mpeg",
        "traceId": "trace-1",
    }


def test_agent_chat_returns_structured_response_and_broadcasts(monkeypatch) -> None:
    broadcast = AsyncMock(return_value=1)
    monkeypatch.setattr(main.pet_event_hub, "broadcast", broadcast)
    monkeypatch.setattr(main, "agent", AgentService(replace(
        main.settings,
        agent_provider="mock",
    )))

    response = TestClient(app).post("/api/agent/chat", json={
        "message": "你好",
        "language": "zh-CN",
        "session_id": "test-session",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "test-session"
    assert body["action_id"] == "speaking"
    assert body["mouth_mode"] == "half-open"
    assert body["requires_confirmation"] is False
    assert body["tool_calls"] == []
    broadcast.assert_awaited_once()
    event = broadcast.await_args.args[0]
    assert event.action_id == "speaking"


def test_agent_chat_rejects_blank_message() -> None:
    response = TestClient(app).post("/api/agent/chat", json={"message": "   "})

    assert response.status_code == 422


def test_agent_chat_uses_mock_fallback_when_provider_fails(monkeypatch) -> None:
    async def unavailable(_request, _references, _history, _memories, _persona=None):
        raise AgentProviderError("文本 Agent 不可用", "NETWORK", 502)

    test_agent = AgentService(replace(
        main.settings,
        agent_provider="qwen",
        agent_api_key="test-key",
        agent_chat_endpoint="https://example.test/chat",
    ))
    monkeypatch.setattr(test_agent.remote_agent, "respond", unavailable)
    monkeypatch.setattr(main, "agent", test_agent)

    response = TestClient(app).post("/api/agent/chat", json={"message": "你好"})

    assert response.status_code == 200
    assert response.json()["trace_id"].startswith("mock-")


def test_agent_chat_strict_remote_mode_rejects_mock_provider(monkeypatch) -> None:
    test_settings = replace(
        main.settings,
        agent_provider="mock",
        agent_require_remote=True,
        agent_fallback_to_mock=False,
    )
    monkeypatch.setattr(main, "agent", AgentService(test_settings))

    response = TestClient(app).post("/api/agent/chat", json={"message": "你好"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REMOTE_AGENT_REQUIRED"


def test_health_reports_remote_agent_configuration_conflicts(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", replace(
        main.settings,
        agent_provider="qwen",
        agent_api_key="",
        agent_chat_endpoint="",
        agent_require_remote=True,
        agent_fallback_to_mock=True,
    ))

    body = TestClient(app).get("/api/health").json()

    assert body["agentReady"] is False
    assert body["agentRequireRemote"] is True
    assert "remote_required_but_mock_fallback_enabled" in body["agentConfigurationIssues"]
    assert any(
        issue.startswith("remote_configuration_incomplete:")
        for issue in body["agentConfigurationIssues"]
    )


def test_agent_event_websocket_returns_correlated_status_response_and_action(monkeypatch) -> None:
    test_agent = AgentService(replace(main.settings, agent_provider="mock"))
    monkeypatch.setattr(main, "agent", test_agent)
    broadcast = AsyncMock(return_value=0)
    monkeypatch.setattr(main.pet_event_hub, "broadcast", broadcast)

    with TestClient(app) as client:
        with client.websocket_connect("/api/agent/events") as websocket:
            websocket.send_json({
                "type": "agent.message",
                "request_id": "request-1",
                "session_id": "session-1",
                "message": "你好",
                "language": "zh-CN",
            })

            thinking = websocket.receive_json()
            response = websocket.receive_json()
            action = websocket.receive_json()
            completed = websocket.receive_json()

    assert thinking == {
        "type": "agent.status",
        "request_id": "request-1",
        "session_id": "session-1",
        "status": "thinking",
    }
    assert response["type"] == "agent.response"
    assert response["request_id"] == "request-1"
    assert response["session_id"] == "session-1"
    assert response["response"]["action_id"] == "speaking"
    assert action == {
        "type": "pet.action",
        "request_id": "request-1",
        "session_id": "session-1",
        "action": {
            "type": "pet.action",
            "action_id": "speaking",
            "emotion": "calm",
            "mouth_mode": "half-open",
            "duration_ms": None,
            "interruptible": True,
        },
    }
    assert completed == {
        "type": "agent.status",
        "request_id": "request-1",
        "session_id": "session-1",
        "status": "completed",
    }
    broadcast.assert_awaited_once()


def test_agent_event_websocket_rejects_invalid_message_without_closing_connection() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/api/agent/events") as websocket:
            websocket.send_json({
                "type": "agent.message",
                "request_id": "request-2",
                "session_id": "session-2",
                "message": " ",
            })
            assert websocket.receive_json() == {
                "type": "agent.error",
                "request_id": "request-2",
                "session_id": "session-2",
                "code": "INVALID_MESSAGE",
                "message": "Agent 事件格式无效",
            }


def test_agent_event_websocket_contains_provider_error(monkeypatch) -> None:
    async def unavailable(_request):
        raise AgentProviderError("文本 Agent 不可用", "NETWORK", 502)

    test_agent = AgentService(replace(main.settings, agent_provider="qwen"))
    monkeypatch.setattr(test_agent, "respond", unavailable)
    monkeypatch.setattr(main, "agent", test_agent)

    with TestClient(app) as client:
        with client.websocket_connect("/api/agent/events") as websocket:
            websocket.send_json({
                "type": "agent.message",
                "request_id": "request-3",
                "session_id": "session-3",
                "message": "hello",
            })
            assert websocket.receive_json()["status"] == "thinking"
            assert websocket.receive_json() == {
                "type": "agent.error",
                "request_id": "request-3",
                "session_id": "session-3",
                "code": "NETWORK",
                "message": "文本 Agent 不可用",
            }


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [WebSocketDisconnect(code=1000), RuntimeError("socket closed")])
async def test_agent_event_send_failure_is_treated_as_client_disconnect(error) -> None:
    class ClosedWebSocket:
        async def send_json(self, _payload) -> None:
            raise error

    assert await main._try_send_agent_event(ClosedWebSocket(), {"type": "agent.status"}) is False


def test_clear_agent_session_removes_server_side_context(monkeypatch) -> None:
    test_agent = AgentService(replace(main.settings, agent_provider="mock"))
    monkeypatch.setattr(main, "agent", test_agent)

    with TestClient(app) as client:
        chat = client.post("/api/agent/chat", json={
            "message": "你好",
            "session_id": "clear-session",
        })
        assert chat.status_code == 200

        cleared = client.delete("/api/agent/sessions/clear-session")
        cleared_again = client.delete("/api/agent/sessions/clear-session")

    assert cleared.status_code == 200
    assert cleared.json() == {"session_id": "clear-session", "cleared": True}
    assert cleared_again.status_code == 200
    assert cleared_again.json() == {"session_id": "clear-session", "cleared": False}


def test_memory_routes_confirm_edit_and_delete_candidates(monkeypatch, tmp_path) -> None:
    test_agent = AgentService(
        replace(main.settings, agent_provider="mock"),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
    )
    candidate = test_agent.memory_store.create_candidates("memory-session", [
        MemorySuggestion(content="称呼我为小明", category="preference"),
    ])[0]
    monkeypatch.setattr(main, "agent", test_agent)
    monkeypatch.setattr(main, "identity", IdentityService(MockVoiceprintAdapter()))

    with TestClient(app) as client:
        verified = client.post("/api/identity/mock/verify", json={"sample": "owner"})
        assert verified.status_code == 200
        pending = client.get("/api/memories/candidates")
        assert pending.status_code == 200
        assert pending.json()[0]["id"] == candidate.id

        confirmed = client.post(
            f"/api/memories/candidates/{candidate.id}/confirm",
            json={"content": "称呼我为小明", "category": "preference"},
        )
        assert confirmed.status_code == 200
        memory_id = confirmed.json()["id"]

        edited = client.patch(
            f"/api/memories/{memory_id}",
            json={"content": "称呼我为明", "category": "preference"},
        )
        assert edited.status_code == 200
        assert edited.json()["content"] == "称呼我为明"

        deleted = client.delete(f"/api/memories/{memory_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}


def test_memory_routes_require_owner_verification(monkeypatch, tmp_path) -> None:
    test_agent = AgentService(
        replace(main.settings, agent_provider="mock"),
        memory_store=MemoryStore(tmp_path / "memory.sqlite3"),
    )
    monkeypatch.setattr(main, "agent", test_agent)
    monkeypatch.setattr(main, "identity", IdentityService(MockVoiceprintAdapter()))
    main.identity.reset()

    with TestClient(app) as client:
        locked = client.get("/api/memories")
        assert locked.status_code == 403
        assert locked.json()["detail"]["code"] == "OWNER_VERIFICATION_REQUIRED"

        verified = client.post("/api/identity/mock/verify", json={"sample": "owner"})
        assert verified.status_code == 200
        assert verified.json()["status"] == "owner_verified"
        assert client.get("/api/memories").status_code == 200


def test_controlled_tool_routes_keep_file_metadata_behind_owner_gate(monkeypatch, tmp_path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(
        main,
        "tools",
        ControlledToolService(tmp_path / "tools.sqlite3", allowed_directories=(allowed,)),
    )
    monkeypatch.setattr(main, "identity", IdentityService(MockVoiceprintAdapter()))
    main.identity.reset()

    with TestClient(app) as client:
        definitions = client.get("/api/tools")
        now = client.post("/api/tools/execute", json={"tool_name": "get_time", "arguments": {}})
        locked_approvals = client.get("/api/tools/approvals")
        locked_audit = client.get("/api/tools/audit")
        locked_search = client.post("/api/tools/execute", json={
            "tool_name": "search_files",
            "arguments": {"root_path": str(allowed), "pattern": "*.txt"},
        })
        verified = client.post("/api/identity/mock/verify", json={"sample": "owner"})
        pending = client.post("/api/tools/execute", json={
            "tool_name": "open_file",
            "arguments": {"path": str(target)},
            "session_id": "tool-route-session",
        })
        approvals = client.get("/api/tools/approvals")
        audit = client.get("/api/tools/audit")

    assert definitions.status_code == 200
    assert now.status_code == 200
    assert now.json()["status"] == "success"
    assert locked_approvals.status_code == 403
    assert locked_audit.status_code == 403
    assert locked_search.status_code == 403
    assert verified.status_code == 200
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert approvals.json()[0]["session_id"] == "tool-route-session"
    assert audit.json()[0]["tool_name"] == "open_file"


def test_local_state_routes_require_owner_verification(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "local_state", LocalStateStore(tmp_path / "local-state.sqlite3"))
    main.identity.temporary_open_access = False
    main.identity.reset()

    with TestClient(app) as client:
        assert client.get("/api/reminders").status_code == 403
        assert client.get("/api/settings").status_code == 403
        assert client.get("/api/system/logs").status_code == 403


def test_temporary_open_access_bypasses_owner_verification(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "local_state", LocalStateStore(tmp_path / "local-state.sqlite3"))
    main.identity.temporary_open_access = True
    main.identity.reset()

    with TestClient(app) as client:
        snapshot = client.get("/api/identity")
        assert snapshot.status_code == 200
        assert snapshot.json()["temporary_open_access"] is True
        assert snapshot.json()["status"] == "owner_verified"
        assert client.get("/api/reminders").status_code == 200
        assert client.get("/api/settings").status_code == 200


def test_local_state_routes_persist_owner_reminders_and_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "local_state", LocalStateStore(tmp_path / "local-state.sqlite3"))
    monkeypatch.setattr(main, "identity", IdentityService(MockVoiceprintAdapter()))
    main.identity.reset()

    with TestClient(app) as client:
        assert client.post("/api/identity/mock/verify", json={"sample": "owner"}).status_code == 200
        created = client.post("/api/reminders", json={
            "title": "喝水",
            "remindAt": "2099-01-01T00:00:00+00:00",
            "sessionId": "local-state-route",
        })
        assert created.status_code == 200
        reminder_id = created.json()["id"]

        updated = client.patch(f"/api/reminders/{reminder_id}", json={"title": "休息一下"})
        assert updated.status_code == 200
        assert updated.json()["title"] == "休息一下"

        settings = client.patch("/api/settings", json={
            "language": "ja-JP",
            "personality": "concise",
            "voice_preference": "gentle",
            "memory_policy": "disabled",
            "diagnostics_enabled": False,
        })
        assert settings.status_code == 200
        assert settings.json()["language"] == "ja-JP"
        assert settings.json()["permission_mode"] == "owner_confirmation"

        cancelled = client.delete(f"/api/reminders/{reminder_id}")
        logs = client.get("/api/system/logs")

    assert cancelled.json() == {"deleted": True}
    assert [item["event_type"] for item in logs.json()] == [
        "reminder.cancelled",
        "settings.updated",
        "reminder.updated",
        "reminder.created",
        "identity.verification_succeeded",
    ]


def test_agent_chat_uses_rag_and_returns_display_only_sources(monkeypatch) -> None:
    test_rag = RagService(
        replace(
            main.settings,
            rag_embedding_provider="hash",
            rag_embedding_dimension=128,
            rag_chunk_size=100,
            rag_chunk_overlap=20,
        ),
        store=InMemoryRagStore(),
        embedder=HashEmbeddingAdapter(128),
    )
    monkeypatch.setattr(main, "rag", test_rag)
    monkeypatch.setattr(main, "agent", AgentService(
        replace(main.settings, agent_provider="mock"),
        rag_service=test_rag,
    ))

    with TestClient(app) as client:
        ingest = client.post(
            "/api/rag/documents",
            data={"collection": "character_knowledge", "source_label": "character guide"},
            files={"document": ("character.md", b"The desktop pet renderer uses Godot.", "text/markdown")},
        )
        assert ingest.status_code == 200

        response = client.post("/api/agent/chat", json={
            "message": "桌宠使用什么渲染器？",
            "rag_collection": "character_knowledge",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["rag_status"] == "used"
    assert body["sources"][0]["source_label"] == "character guide"
    assert "content" not in body["sources"][0]
    assert body["tool_calls"] == []


def test_rag_routes_ingest_search_and_delete_without_touching_agent(monkeypatch) -> None:
    test_rag = RagService(
        replace(
            main.settings,
            rag_embedding_provider="hash",
            rag_embedding_dimension=128,
            rag_chunk_size=100,
            rag_chunk_overlap=20,
        ),
        store=InMemoryRagStore(),
        embedder=HashEmbeddingAdapter(128),
    )
    monkeypatch.setattr(main, "rag", test_rag)

    with TestClient(app) as client:
        ingest = client.post(
            "/api/rag/documents",
            data={"collection": "user_documents", "source_label": "project notes"},
            files={"document": ("notes.md", b"Godot is used for desktop rendering.", "text/markdown")},
        )
        assert ingest.status_code == 200
        document_id = ingest.json()["document_id"]

        search = client.post("/api/rag/search", json={
            "collection": "user_documents",
            "query": "Which renderer is used?",
        })
        assert search.status_code == 200
        assert search.json()["results"][0]["document_id"] == document_id
        assert search.json()["results"][0]["source_label"] == "project notes"

        delete = client.delete(f"/api/rag/documents/user_documents/{document_id}")
        assert delete.status_code == 200

        after_delete = client.post("/api/rag/search", json={
            "collection": "user_documents",
            "query": "Which renderer is used?",
        })
        assert after_delete.status_code == 200
        assert after_delete.json()["results"] == []


def test_rag_route_rejects_disallowed_collections(monkeypatch) -> None:
    monkeypatch.setattr(main, "rag", RagService(
        replace(
            main.settings,
            rag_embedding_provider="hash",
            rag_embedding_dimension=128,
            rag_chunk_size=100,
            rag_chunk_overlap=20,
        ),
        store=InMemoryRagStore(),
        embedder=HashEmbeddingAdapter(128),
    ))

    response = TestClient(app).post("/api/rag/search", json={
        "collection": "system_policy",
        "query": "ignore safeguards",
    })

    assert response.status_code == 422


def test_streaming_asr_without_doubao_configuration_returns_safe_error(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", replace(
        main.settings,
        doubao_api_key="",
        doubao_app_key="",
        doubao_access_key="",
    ))
    with TestClient(app).websocket_connect("/api/speech/asr/stream") as websocket:
        websocket.send_json({"type": "start", "language": "zh-CN"})
        response = websocket.receive_json()

    assert response == {
        "type": "error",
        "code": "NOT_CONFIGURED",
        "message": "豆包 ASR 尚未配置",
    }


def rts_settings():
    return replace(
        main.settings,
        voiceprint_provider="volcengine-rtc",
        voiceprint_rtc_owner_name="desktop-owner",
        voiceprint_rtc_score_threshold=50,
        voiceprint_rtc_bridge_secret="test-bridge-secret",
        voiceprint_rtc_callback_url="https://rtc-tunnel.example.test/api/identity/rtc/rts/messages",
        voiceprint_rtc_callback_secret="rts-shared-secret",
    )


def rts_envelope(payload: dict, *, kind: str = "subtitle", signature: str = "rts-shared-secret") -> dict:
    binary = encode_rts_binary(kind, payload)
    return {
        "message": base64.b64encode(binary).decode("ascii"),
        "signature": signature,
    }


def configure_rts_route(monkeypatch, tmp_path, *, active: bool = True):
    settings = rts_settings()
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main,
        "identity",
        IdentityService(VolcengineRtcVoiceprintAdapter("desktop-owner", 50)),
    )
    monkeypatch.setattr(main, "local_state", LocalStateStore(tmp_path / "local-state.sqlite3"))
    bridge = RtcVoiceprintBridge(settings)
    if active:
        bridge.register_active_session(
            RtcVoiceChatSession(taskId="rtc-task", roomId="room-1"),
            ["desktop-owner"],
        )
    monkeypatch.setattr(main, "rtc_voiceprint_bridge", bridge)
    return bridge


def test_rtc_rts_get_probe_returns_ok() -> None:
    response = TestClient(app).get("/api/identity/rtc/rts/messages")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_rtc_rts_subtitle_verifies_owner_without_exposing_text_or_voiceprint_id(
    monkeypatch,
    tmp_path,
) -> None:
    configure_rts_route(monkeypatch, tmp_path)
    body = rts_envelope({
        "type": "subtitle",
        "data": [{
            "text": "这是私有声纹字幕",
            "language": "zh-CN",
            "userId": "desktop-owner",
            "voiceprintId": "voiceprint-secret-id",
            "voiceprintName": "desktop-owner",
            "voiceprintScore": 52,
            "definite": True,
            "paragraph": True,
        }],
    })

    with TestClient(app) as client:
        response = client.post("/api/identity/rtc/rts/messages", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["identityApplied"] is True
    assert payload["identity"]["status"] == "owner_verified"
    assert payload["identity"]["can_read_private_memory"] is True
    assert "这是私有声纹字幕" not in response.text
    assert "voiceprint-secret-id" not in response.text
    assert "rts-shared-secret" not in response.text


def test_rtc_rts_status_message_does_not_grant_identity(monkeypatch, tmp_path) -> None:
    configure_rts_route(monkeypatch, tmp_path)
    body = rts_envelope(
        {"event": "VoicePrintStatus", "status": "Active"},
        kind="voiceprint_status",
    )

    response = TestClient(app).post("/api/identity/rtc/rts/messages", json=body)

    assert response.status_code == 200
    assert response.json()["identityApplied"] is False
    assert main.identity.snapshot().status == "unknown"


def test_rtc_rts_ai_or_partial_subtitle_does_not_grant_identity(monkeypatch, tmp_path) -> None:
    configure_rts_route(monkeypatch, tmp_path)
    body = rts_envelope({
        "type": "subtitle",
        "data": [
            {"userId": "desktop-pet-agent", "voiceprintName": "desktop-owner", "voiceprintScore": 99, "definite": True, "paragraph": True},
            {"userId": "desktop-owner", "voiceprintName": "desktop-owner", "voiceprintScore": 99, "definite": False},
        ],
    })

    response = TestClient(app).post("/api/identity/rtc/rts/messages", json=body)

    assert response.status_code == 200
    assert response.json()["identityApplied"] is False
    assert main.identity.snapshot().status == "unknown"


def test_rtc_rts_unmatched_completed_sentence_marks_guest(monkeypatch, tmp_path) -> None:
    configure_rts_route(monkeypatch, tmp_path)
    body = rts_envelope({
        "type": "subtitle",
        "data": [{"userId": "desktop-owner", "definite": True, "paragraph": True}],
    })

    response = TestClient(app).post("/api/identity/rtc/rts/messages", json=body)

    assert response.status_code == 200
    assert response.json()["identity"]["status"] == "guest"
    assert response.json()["identity"]["can_use_tools"] is False


def test_rtc_rts_rejects_bad_signature_and_inactive_session(monkeypatch, tmp_path) -> None:
    configure_rts_route(monkeypatch, tmp_path)
    bad_signature = rts_envelope(
        {"type": "subtitle", "data": []},
        signature="wrong-secret",
    )

    response = TestClient(app).post("/api/identity/rtc/rts/messages", json=bad_signature)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "RTC_RTS_SIGNATURE_INVALID"

    configure_rts_route(monkeypatch, tmp_path, active=False)
    inactive_body = rts_envelope({
        "type": "subtitle",
        "data": [{
            "userId": "desktop-owner",
            "voiceprintId": "voiceprint-secret-id",
            "voiceprintName": "desktop-owner",
            "voiceprintScore": 52,
            "definite": True,
            "paragraph": True,
        }],
    })
    inactive_response = TestClient(app).post("/api/identity/rtc/rts/messages", json=inactive_body)
    assert inactive_response.status_code == 409
    assert inactive_response.json()["detail"]["code"] == "RTC_SESSION_NOT_ACTIVE"


def test_rag_document_list_route(monkeypatch) -> None:
    from backend.app.rag import RagIngestResponse

    class FakeRag:
        async def list_documents(self, collection: str):
            return [RagIngestResponse(
                collection=collection,
                document_id="12345678-1234-1234-1234-123456789012",
                filename="a.md",
                source_label="a.md",
                chunk_count=2,
                updated_at=123,
                content_hash="hash-1",
            )]

    monkeypatch.setattr(main, "rag", FakeRag())
    response = TestClient(app).get("/api/rag/documents/character_knowledge")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "a.md"
    assert body[0]["content_hash"] == "hash-1"


def test_rag_document_list_route_rejects_bad_collection(monkeypatch) -> None:
    class FakeRag:
        async def list_documents(self, collection: str):
            from backend.app.rag import validate_collection
            validate_collection(collection)
            return []

    monkeypatch.setattr(main, "rag", FakeRag())
    response = TestClient(app).get("/api/rag/documents/not_a_collection")
    assert response.status_code == 422


def test_persona_routes_full_lifecycle(monkeypatch, tmp_path) -> None:
    from backend.app.persona import PersonaStore

    test_store = PersonaStore(tmp_path / "persona.sqlite3")
    monkeypatch.setattr(main, "persona_store", test_store)
    reset_calls: list[bool] = []
    monkeypatch.setattr(
        main.agent,
        "reset_conversation_contexts",
        lambda: reset_calls.append(True),
    )
    client = TestClient(app)

    draft = {
        "profile_name": "傲娇人格",
        "character_name": "miya",
        "personality": "嘴硬心软",
        "speaking_style": "短促带哼声",
        "default_action": "idle",
        "voice_id": "Chinese_huolishaonv",
        "system_prompt": "保持傲娇，但关键时刻要温柔。",
    }
    created = client.post("/api/personas", json=draft)
    assert created.status_code == 200
    profile_id = created.json()["id"]

    listing = client.get("/api/personas")
    assert any(profile["id"] == profile_id for profile in listing.json())

    assert client.get("/api/personas/active").json() is None

    activated = client.post(f"/api/personas/{profile_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    assert client.get("/api/personas/active").json()["id"] == profile_id

    updated = client.patch(
        f"/api/personas/{profile_id}",
        json={**draft, "character_name": "miya2"},
    )
    assert updated.status_code == 200
    assert updated.json()["character_name"] == "miya2"

    versions = client.get(f"/api/personas/{profile_id}/versions")
    assert versions.status_code == 200
    version_id = versions.json()[0]["version_id"]

    rolled_back = client.post(
        f"/api/personas/{profile_id}/rollback",
        json={"version_id": version_id},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["character_name"] == "miya"

    deactivated = client.post("/api/personas/deactivate")
    assert deactivated.status_code == 200
    assert client.get("/api/personas/active").json() is None
    assert len(reset_calls) == 4

    removed = client.delete(f"/api/personas/{profile_id}")
    assert removed.status_code == 200
    assert client.get(f"/api/personas/{profile_id}").status_code == 404


def test_persona_activate_missing_returns_404(monkeypatch, tmp_path) -> None:
    from backend.app.persona import PersonaStore

    monkeypatch.setattr(main, "persona_store", PersonaStore(tmp_path / "p.sqlite3"))
    response = TestClient(app).post("/api/personas/missing/activate")
    assert response.status_code == 404


def test_open_file_uses_interrupt_workflow_when_enabled(
    monkeypatch,
    tmp_path,
) -> None:
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    target_file = allowed_dir / "示例.txt"
    target_file.write_text("测试", encoding="utf-8")

    test_settings = replace(
        main.settings,
        langgraph_approval_interrupt_enabled=True,
        langgraph_checkpoint_enabled=False,
    )
    test_tools = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_directories=(allowed_dir,),
    )
    opened_calls: list[dict[str, object]] = []

    def fake_execute(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        opened_calls.append({"tool_name": tool_name, "arguments": arguments})
        return {"path": arguments["path"], "opened": True}

    test_tools._execute_tool = fake_execute
    test_identity = IdentityService(
        MockVoiceprintAdapter(),
        temporary_open_access=True,
    )
    test_workflow = ToolApprovalWorkflow(
        test_settings,
        test_tools,
        test_identity,
    )

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "tools", test_tools)
    monkeypatch.setattr(main, "identity", test_identity)
    monkeypatch.setattr(main, "tool_approval_workflow", test_workflow)

    with TestClient(app) as client:
        pending = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "open_file",
                "arguments": {"path": str(target_file)},
                "session_id": "interrupt-api-session",
                "idempotency_key": "interrupt-api-key",
            },
        )
        assert pending.status_code == 200
        assert pending.json()["status"] == "pending"

        call_id = pending.json()["call_id"]
        approval = test_tools.get_approval_by_call_id(call_id)
        approved = client.post(
            f"/api/tools/approvals/{approval.approval_id}/approve",
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "success"

        repeated = client.post(
            f"/api/tools/approvals/{approval.approval_id}/approve",
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "APPROVAL_ALREADY_RESOLVED"

    assert len(opened_calls) == 1


def test_langgraph_checkpoint_endpoints_require_owner_and_call_maintenance(
    monkeypatch,
) -> None:
    expected_summary = CheckpointDatabaseSummary(
        enabled=True,
        path="C:/demo/langgraph-checkpoints.sqlite3",
        exists=True,
        size_bytes=128,
        thread_count=0,
        checkpoint_count=0,
        write_count=0,
        threads=[],
    )
    expected_cleanup = CheckpointCleanupResult(
        deleted_thread_ids=[],
        retained_thread_ids=[],
        checkpoint_count_before=0,
        checkpoint_count_after=0,
        write_count_before=0,
        write_count_after=0,
        vacuumed=False,
    )
    fake_maintenance = type(
        "FakeCheckpointMaintenance",
        (),
        {
            "summary": AsyncMock(return_value=expected_summary),
            "cleanup": AsyncMock(return_value=expected_cleanup),
        },
    )()

    monkeypatch.setattr(
        main,
        "identity",
        IdentityService(MockVoiceprintAdapter(), temporary_open_access=True),
    )
    monkeypatch.setattr(main, "checkpoint_maintenance", fake_maintenance)

    response = TestClient(app).get(
        "/api/langgraph/checkpoints?include_runtime=true",
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    fake_maintenance.summary.assert_awaited_once_with(include_runtime=True)

    cleanup_response = TestClient(app).post(
        "/api/langgraph/checkpoints/cleanup",
        json={"only_completed": True, "vacuum": True},
    )

    assert cleanup_response.status_code == 200
    request = fake_maintenance.cleanup.await_args.args[0]
    assert request.only_completed is True
    assert request.delete_all is False
    assert request.vacuum is True
