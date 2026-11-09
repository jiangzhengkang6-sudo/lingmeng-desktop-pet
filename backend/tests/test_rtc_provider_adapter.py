import pytest

from backend.app.identity import NO_VOICEPRINT_MATCH_NAME, RtcVoiceprintObservation
from backend.app.rtc_event_bridge import RtcEventBridgeError
from backend.app.rtc_provider_adapter import (
    RtcProviderEventAdapter,
    RtcProviderEventIgnored,
    create_volcengine_rtc_adapter,
    create_unconfigured_rtc_adapter,
    reject_asr_payload,
)
from scripts.rtc_event_bridge_worker import prepare_event_for_submission


def test_unconfigured_provider_adapter_fails_closed() -> None:
    adapter = create_unconfigured_rtc_adapter("volcengine-rtc")

    with pytest.raises(RtcEventBridgeError, match="尚未注册事件映射器"):
        adapter.adapt({"event": "unknown"})


def test_provider_adapter_requires_explicit_mapper_and_normalizes_result() -> None:
    def mapper(event):
        return {
            "task_id": event["task"],
            "voiceprint_name": event["name"],
            "voiceprint_score": event["score"],
        }

    adapter = RtcProviderEventAdapter("volcengine-rtc", mapper)
    result = adapter.adapt({
        "task": "rtc-task",
        "name": "desktop-owner",
        "score": 52,
    })

    assert result == RtcVoiceprintObservation(
        task_id="rtc-task",
        voiceprint_name="desktop-owner",
        voiceprint_score=52,
    )


def test_provider_adapter_rejects_mapper_output_with_unknown_fields() -> None:
    adapter = RtcProviderEventAdapter(
        "volcengine-rtc",
        lambda event: {
            "task_id": event["task"],
            "voiceprint_name": "desktop-owner",
            "voiceprint_score": 52,
            "transcript": "hello",
        },
    )

    with pytest.raises(RtcEventBridgeError):
        adapter.adapt({"task": "rtc-task"})


def test_sauc_asr_payload_cannot_be_used_for_voiceprint_verification() -> None:
    with pytest.raises(RtcEventBridgeError, match="SAUC"):
        reject_asr_payload({
            "result": {"text": "你好"},
            "additions": {"log_id": "asr-log"},
        })


def test_volcengine_subtitle_callback_maps_one_matched_voiceprint() -> None:
    adapter = create_volcengine_rtc_adapter("local-rtc-task")

    result = adapter.adapt({
        "type": "subtitle",
        "data": [{
            "voiceprintId": "provider-voiceprint-id",
            "voiceprintName": "desktop-owner",
            "voiceprintScore": 52,
        }],
    })

    assert result == RtcVoiceprintObservation(
        task_id="local-rtc-task",
        voiceprint_name="desktop-owner",
        voiceprint_score=52,
    )


def test_volcengine_subtitle_callback_rejects_an_unmatched_voiceprint() -> None:
    adapter = create_volcengine_rtc_adapter("local-rtc-task")

    with pytest.raises(RtcProviderEventIgnored, match="未匹配") as error:
        adapter.adapt({
            "type": "subtitle",
            "data": [{
                "voiceprintId": None,
                "voiceprintName": None,
                "voiceprintScore": 12,
            }],
        })
    assert error.value.observation is not None
    assert error.value.observation.voiceprint_name == NO_VOICEPRINT_MATCH_NAME
    assert error.value.observation.voiceprint_score == 1


def test_volcengine_subtitle_callback_rejects_unrelated_or_ambiguous_events() -> None:
    adapter = create_volcengine_rtc_adapter("local-rtc-task")

    with pytest.raises(RtcEventBridgeError, match="仅 subtitle"):
        adapter.adapt({"type": "voiceprint_status", "status": "success"})
    with pytest.raises(RtcEventBridgeError, match="多个"):
        adapter.adapt({
            "type": "subtitle",
            "data": [
                {"voiceprintName": "desktop-owner", "voiceprintScore": 52},
                {"voiceprintName": "other-owner", "voiceprintScore": 54},
            ],
        })


def test_volcengine_subtitle_callback_requires_a_trusted_task_context() -> None:
    with pytest.raises(RtcEventBridgeError, match="task_id"):
        create_volcengine_rtc_adapter("").adapt({
            "type": "subtitle",
            "data": [{"voiceprintName": "desktop-owner", "voiceprintScore": 52}],
        })


def test_worker_preparation_only_returns_mapped_subtitle_events() -> None:
    matched = prepare_event_for_submission(
        {
            "type": "subtitle",
            "data": [{"voiceprintName": "desktop-owner", "voiceprintScore": 52}],
        },
        provider="volcengine-rtc",
        task_id="trusted-task",
    )
    status = prepare_event_for_submission(
        {"type": "voiceprint_status", "status": "success"},
        provider="volcengine-rtc",
        task_id="trusted-task",
    )

    assert matched == RtcVoiceprintObservation(
        task_id="trusted-task",
        voiceprint_name="desktop-owner",
        voiceprint_score=52,
    )
    assert status is None
