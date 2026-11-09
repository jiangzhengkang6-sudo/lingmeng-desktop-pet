from __future__ import annotations

import base64
import json

import pytest

from backend.app.identity import NO_VOICEPRINT_MATCH_NAME, RtcVoiceprintObservation
from backend.app.rtc_rts import (
    RtsIdentitySelection,
    RtsMessageError,
    RtsSignatureError,
    encode_rts_binary,
    parse_rts_message,
    select_identity_observation,
)


def envelope(kind: str, payload: dict, *, secret: str = "rts-secret") -> bytes:
    binary = encode_rts_binary(kind, payload)
    return json.dumps({
        "message": base64.b64encode(binary).decode("ascii"),
        "signature": secret,
    }).encode("utf-8")


def test_parse_rts_subtitle_message() -> None:
    payload = {"type": "subtitle", "data": [{"text": "你好"}]}
    message = parse_rts_message(
        envelope("subtitle", payload),
        callback_secret="rts-secret",
    )

    assert message.kind == "subtitle"
    assert message.payload == payload


def test_parse_rts_status_message() -> None:
    payload = {"event": "VoicePrintStatus", "status": "Active"}
    message = parse_rts_message(
        envelope("voiceprint_status", payload),
        callback_secret="rts-secret",
    )

    assert message.kind == "voiceprint_status"
    assert message.payload["status"] == "Active"


def test_parse_rts_rejects_bad_signature_and_binary() -> None:
    with pytest.raises(RtsSignatureError):
        parse_rts_message(
            envelope("subtitle", {"type": "subtitle", "data": []}, secret="wrong"),
            callback_secret="rts-secret",
        )

    raw = encode_rts_binary("subtitle", {"type": "subtitle", "data": []})
    corrupted = raw[:4] + (len(raw) - 7).to_bytes(4, "big") + raw[8:]
    body = json.dumps({
        "message": base64.b64encode(corrupted).decode("ascii"),
        "signature": "rts-secret",
    }).encode("utf-8")
    with pytest.raises(RtsMessageError, match="长度"):
        parse_rts_message(body, callback_secret="rts-secret")


def test_select_owner_from_completed_human_subtitle() -> None:
    selection = select_identity_observation(
        {
            "type": "subtitle",
            "data": [{
                "userId": "desktop-owner",
                "voiceprintId": "voiceprint-id",
                "voiceprintName": "desktop-owner",
                "voiceprintScore": 52,
                "definite": True,
                "paragraph": True,
            }],
        },
        task_id="rtc-task",
        target_user_ids=["desktop-owner"],
    )

    assert selection == RtsIdentitySelection(
        observation=RtcVoiceprintObservation(
            task_id="rtc-task",
            voiceprint_name="desktop-owner",
            voiceprint_score=52,
        )
    )


def test_select_ignores_ai_partial_and_other_users_until_owner_sentence_completes() -> None:
    selection = select_identity_observation(
        {
            "type": "subtitle",
            "data": [
                {"userId": "desktop-pet-agent", "voiceprintName": "bot", "voiceprintScore": 99},
                {"userId": "other-user", "voiceprintName": "other", "voiceprintScore": 99},
                {"userId": "desktop-owner", "voiceprintName": "desktop-owner", "voiceprintScore": 88, "definite": False},
                {"userId": "desktop-owner", "voiceprintName": "desktop-owner", "voiceprintScore": 88, "paragraph": True},
            ],
        },
        task_id="rtc-task",
        target_user_ids=["desktop-owner"],
    )

    assert selection.observation is None


def test_completed_human_sentence_without_voiceprint_is_unmatched() -> None:
    selection = select_identity_observation(
        {
            "type": "subtitle",
            "data": [{"userId": "desktop-owner", "definite": True, "paragraph": True}],
        },
        task_id="rtc-task",
        target_user_ids=["desktop-owner"],
    )

    assert selection.observation == RtcVoiceprintObservation(
        task_id="rtc-task",
        voiceprint_name=NO_VOICEPRINT_MATCH_NAME,
        voiceprint_score=1,
    )



def test_completed_human_sentence_with_empty_identity_and_score_is_unmatched() -> None:
    selection = select_identity_observation(
        {
            "type": "subtitle",
            "data": [{
                "userId": "desktop-owner",
                "voiceprintId": None,
                "voiceprintName": None,
                "voiceprintScore": 12,
                "definite": True,
                "paragraph": True,
            }],
        },
        task_id="rtc-task",
        target_user_ids=["desktop-owner"],
    )

    assert selection.observation == RtcVoiceprintObservation(
        task_id="rtc-task",
        voiceprint_name=NO_VOICEPRINT_MATCH_NAME,
        voiceprint_score=12,
    )

def test_select_rejects_ambiguous_or_incomplete_voiceprint_fields() -> None:
    with pytest.raises(RtsMessageError, match="多个"):
        select_identity_observation(
            {"type": "subtitle", "data": [
                {"userId": "desktop-owner", "voiceprintId": "a", "voiceprintName": "desktop-owner", "voiceprintScore": 60, "definite": True, "paragraph": True},
                {"userId": "desktop-owner", "voiceprintId": "b", "voiceprintName": "desktop-owner", "voiceprintScore": 61, "definite": True, "paragraph": True},
            ]},
            task_id="rtc-task",
            target_user_ids=["desktop-owner"],
        )

    with pytest.raises(RtsMessageError, match="声纹字段"):
        select_identity_observation(
            {"type": "subtitle", "data": [
                {"userId": "desktop-owner", "voiceprintName": "desktop-owner", "definite": True, "paragraph": True},
            ]},
            task_id="rtc-task",
            target_user_ids=["desktop-owner"],
        )
