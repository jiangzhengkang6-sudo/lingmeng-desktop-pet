from __future__ import annotations

import pytest

from backend.app.persona import (
    PersonaProfileDraft,
    PersonaStore,
    build_persona_prompt_block,
)


def make_draft(**overrides: object) -> PersonaProfileDraft:
    base: dict[str, object] = {
        "profile_name": "傲娇人格",
        "character_name": "miya",
        "personality": "嘴硬心软、外冷内热",
        "speaking_style": "短促、带一点哼声，喜欢用反问",
        "default_action": "idle",
        "voice_id": "Chinese_huolishaonv",
        "system_prompt": "始终保持傲娇，但关键时刻要温柔护短。",
    }
    base.update(overrides)
    return PersonaProfileDraft(**base)  # type: ignore[arg-type]


@pytest.fixture
def store(tmp_path: pytest.TempPathFactory) -> PersonaStore:  # type: ignore[annotation-unchecked]
    return PersonaStore(tmp_path / "persona.sqlite3")  # type: ignore[operator]


def test_create_and_get_profile(store: PersonaStore) -> None:
    profile = store.create_profile(make_draft())
    assert profile.id.startswith("persona_")
    assert profile.is_active is False
    loaded = store.get_profile(profile.id)
    assert loaded is not None
    assert loaded.character_name == "miya"
    assert loaded.voice_id == "Chinese_huolishaonv"


def test_invalid_default_action_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_draft(default_action="fly-away")


def test_activate_is_exclusive(store: PersonaStore) -> None:
    first = store.create_profile(make_draft(profile_name="A"))
    second = store.create_profile(make_draft(profile_name="B"))

    store.activate(first.id)
    active = store.get_active()
    assert active is not None
    assert active.id == first.id

    store.activate(second.id)
    assert store.get_active() is not None
    assert store.get_active().id == second.id
    assert store.get_profile(first.id) is not None
    assert store.get_profile(first.id).is_active is False


def test_deactivate_all(store: PersonaStore) -> None:
    profile = store.create_profile(make_draft())
    store.activate(profile.id)
    store.deactivate_all()
    assert store.get_active() is None


def test_update_keeps_version_and_rollback(store: PersonaStore) -> None:
    profile = store.create_profile(make_draft(character_name="old-name"))
    store.update_profile(profile.id, make_draft(character_name="new-name"))
    assert store.get_profile(profile.id) is not None
    assert store.get_profile(profile.id).character_name == "new-name"

    versions = store.list_versions(profile.id)
    assert len(versions) == 1
    assert versions[0].snapshot.character_name == "old-name"

    rolled_back = store.rollback(profile.id, versions[0].version_id)
    assert rolled_back is not None
    assert rolled_back.character_name == "old-name"
    # 回滚前会再保存一个“回滚前快照”
    assert len(store.list_versions(profile.id)) == 2


def test_rollback_unknown_returns_none(store: PersonaStore) -> None:
    profile = store.create_profile(make_draft())
    assert store.rollback(profile.id, "missing-version") is None


def test_delete_profile_removes_versions(store: PersonaStore) -> None:
    profile = store.create_profile(make_draft())
    store.update_profile(profile.id, make_draft(character_name="other"))
    assert store.delete_profile(profile.id) is True
    assert store.get_profile(profile.id) is None
    assert store.list_versions(profile.id) == []


def test_get_missing_profile(store: PersonaStore) -> None:
    assert store.get_profile("missing") is None


def test_delete_missing_profile(store: PersonaStore) -> None:
    assert store.delete_profile("missing") is False


def test_build_persona_prompt_block(store: PersonaStore) -> None:
    profile = store.create_profile(make_draft())
    block = build_persona_prompt_block(profile)
    assert "miya" in block
    assert "嘴硬心软" in block
    assert "Chinese_huolishaonv" in block
