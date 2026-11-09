import pytest

from backend.app.identity import (
    NO_VOICEPRINT_MATCH_NAME,
    IdentityService,
    MockVoiceprintAdapter,
    RtcVoiceprintObservation,
    UnavailableVoiceprintAdapter,
    VolcengineRtcVoiceprintAdapter,
    VoiceprintAdapterUnavailableError,
)


@pytest.mark.asyncio
async def test_mock_identity_starts_locked_and_verifies_owner() -> None:
    service = IdentityService(MockVoiceprintAdapter())

    assert service.snapshot().status == "unknown"
    assert service.snapshot().can_read_private_memory is False

    owner = await service.verify(b"desktop-pet-mock-owner")
    assert owner.status == "owner_verified"
    assert owner.can_read_private_memory is True
    assert owner.can_use_tools is True


@pytest.mark.asyncio
async def test_failed_mock_verification_becomes_guest_and_reset_locks_again() -> None:
    service = IdentityService(MockVoiceprintAdapter())

    guest = await service.verify(b"desktop-pet-mock-guest")
    assert guest.status == "guest"
    assert guest.can_read_private_memory is False
    assert guest.can_use_tools is False

    reset = service.reset()
    assert reset.status == "unknown"
    assert reset.can_read_private_memory is False


@pytest.mark.asyncio
async def test_unavailable_provider_never_grants_owner_identity() -> None:
    service = IdentityService(UnavailableVoiceprintAdapter("volcengine"))

    with pytest.raises(VoiceprintAdapterUnavailableError):
        await service.verify(b"audio")

    assert service.snapshot().status == "unknown"


@pytest.mark.asyncio
async def test_rtc_observation_requires_matching_name_and_score() -> None:
    service = IdentityService(VolcengineRtcVoiceprintAdapter(
        owner_name="desktop-owner",
        score_threshold=50,
    ))

    guest = await service.verify_rtc_observation(RtcVoiceprintObservation(
        task_id="rtc-task",
        voiceprint_name="desktop-owner",
        voiceprint_score=49,
    ))
    assert guest.status == "guest"

    owner = await service.verify_rtc_observation(RtcVoiceprintObservation(
        task_id="rtc-task",
        voiceprint_name="desktop-owner",
        voiceprint_score=50,
    ))
    assert owner.status == "owner_verified"
