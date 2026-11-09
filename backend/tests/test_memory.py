from backend.app.memory import MemoryDraft, MemoryStore


def test_memory_candidates_require_confirmation_and_can_be_removed(tmp_path) -> None:
    store = MemoryStore(tmp_path / "desktop-pet.sqlite3")
    candidate = store.create_candidates("session-a", [
        MemoryDraft(content="我喜欢抹茶", category="preference"),
    ])[0]

    assert [item.content for item in store.list_candidates()] == ["我喜欢抹茶"]
    assert store.context(10) == ()

    confirmed = store.confirm_candidate(
        candidate.id,
        MemoryDraft(content="我喜欢喝抹茶", category="preference"),
    )
    assert confirmed is not None
    assert confirmed.content == "我喜欢喝抹茶"
    assert store.list_candidates() == []
    assert [item.content for item in store.context(10)] == ["我喜欢喝抹茶"]

    updated = store.update_memory(
        confirmed.id,
        MemoryDraft(content="我喜欢喝无糖抹茶", category="preference"),
    )
    assert updated is not None
    assert updated.content == "我喜欢喝无糖抹茶"
    assert store.delete_memory(confirmed.id) is True
    assert store.list_memories() == []


def test_memory_store_deduplicates_candidates_and_rejects_sensitive_content(tmp_path) -> None:
    store = MemoryStore(tmp_path / "desktop-pet.sqlite3")
    first = store.create_candidates("session-a", [
        MemoryDraft(content="我常用中文交流", category="preference"),
    ])
    duplicate = store.create_candidates("session-b", [
        MemoryDraft(content="我常用中文交流", category="preference"),
    ])

    assert first[0].id == duplicate[0].id
    assert len(store.list_candidates()) == 1
