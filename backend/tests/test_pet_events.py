from fastapi.testclient import TestClient

from backend.app.main import app


def test_pet_event_route_accepts_snake_case_and_returns_safe_payload() -> None:
    response = TestClient(app).post("/api/pet/events", json={
        "type": "pet.action",
        "action_id": "speaking",
        "emotion": "happy",
        "mouth_mode": "open",
        "duration_ms": 1000,
        "interruptible": True,
    })

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "delivered": 0,
        "event": {
            "type": "pet.action",
            "action_id": "speaking",
            "emotion": "happy",
            "mouth_mode": "open",
            "duration_ms": 1000,
            "interruptible": True,
        },
    }


def test_pet_event_route_accepts_camel_case() -> None:
    response = TestClient(app).post("/api/pet/events", json={
        "type": "pet.action",
        "actionId": "success",
        "mouthMode": "closed",
        "durationMs": 500,
    })

    assert response.status_code == 200
    assert response.json()["event"]["action_id"] == "success"
    assert response.json()["event"]["mouth_mode"] == "closed"


def test_pet_event_route_rejects_invalid_values() -> None:
    for payload in (
        {"type": "pet.action", "action_id": "dance"},
        {"type": "pet.action", "action_id": "idle", "mouth_mode": "wide"},
        {"type": "pet.action", "action_id": "idle", "duration_ms": 600001},
        {"type": "pet.action", "action_id": "idle", "unexpected": True},
    ):
        response = TestClient(app).post("/api/pet/events", json=payload)
        assert response.status_code == 422


def test_pet_event_websocket_receives_published_event() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/pet/events") as websocket:
        response = client.post("/api/pet/events", json={
            "type": "pet.action",
            "actionId": "thinking",
            "durationMs": 250,
        })

        assert response.status_code == 200
        assert response.json()["delivered"] == 1
        assert websocket.receive_json() == {
            "type": "pet.action",
            "action_id": "thinking",
            "emotion": None,
            "mouth_mode": None,
            "duration_ms": 250,
            "interruptible": True,
        }
