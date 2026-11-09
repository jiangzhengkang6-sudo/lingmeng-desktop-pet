import pytest

from backend.app.config import Settings
from backend.app.rag import (
    CHUNK_ID_MAX_LENGTH,
    HashEmbeddingAdapter,
    InMemoryRagStore,
    MilvusRagStore,
    RagError,
    RagSearchRequest,
    RagService,
    SqliteVecRagStore,
    decode_text_document,
    split_document,
)


def rag_settings() -> Settings:
    return Settings(
        speech_provider="minimax",
        speech_model="speech-2.8-hd",
        speech_api_base_url="https://api.example.test",
        speech_api_key="",
        speech_tts_endpoint="",
        speech_asr_endpoint="",
        speech_voice_id="",
        speech_timeout_seconds=3.0,
        cors_origins=("http://127.0.0.1:5173",),
        rag_embedding_provider="hash",
        rag_embedding_model="local-hash-v1",
        rag_embedding_dimension=128,
        rag_chunk_size=100,
        rag_chunk_overlap=20,
    )


def sqlite_rag_settings(tmp_path) -> Settings:
    settings = rag_settings()
    return Settings(
        **{
            **settings.__dict__,
            "rag_store": "sqlite-vec",
            "rag_sqlite_path": tmp_path / "rag.sqlite3",
        }
    )


def test_text_decoder_rejects_non_text_and_too_large_uploads() -> None:
    with pytest.raises(RagError) as unsupported:
        decode_text_document("notes.pdf", "application/pdf", b"not a real pdf", 100)
    assert unsupported.value.status_code == 415

    with pytest.raises(RagError) as too_large:
        decode_text_document("notes.txt", "text/plain", b"12345", 4)
    assert too_large.value.status_code == 413


def test_rag_store_settings_read_sqlite_path(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "rag.sqlite3"
    monkeypatch.setenv("RAG_STORE", "sqlite-vec")
    monkeypatch.setenv("RAG_SQLITE_PATH", str(database_path))

    settings = Settings.from_environment()

    assert settings.rag_store == "sqlite-vec"
    assert settings.rag_sqlite_path == database_path


def test_rag_store_settings_reject_unknown_store(monkeypatch) -> None:
    monkeypatch.setenv("RAG_STORE", "unknown-store")

    assert Settings.from_environment().rag_store == "milvus"


def test_rag_sqlite_database_is_separate_from_memory_database() -> None:
    settings = rag_settings()

    assert settings.rag_sqlite_path.name == "rag.sqlite3"
    assert settings.rag_sqlite_path != settings.memory_database_path


def test_chunker_keeps_content_and_applies_overlap() -> None:
    text = "alpha " * 40
    chunks = split_document(text, chunk_size=80, overlap=20)

    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
    assert chunks[0].chunk_index == 0
    assert chunks[-1].chunk_index == len(chunks) - 1
    assert chunks[0].content[-10:] in chunks[1].content


@pytest.mark.asyncio
async def test_rag_service_keeps_collections_isolated_and_deletes_documents() -> None:
    store = InMemoryRagStore()
    service = RagService(
        rag_settings(),
        store=store,
        embedder=HashEmbeddingAdapter(128),
    )
    character = await service.ingest(
        collection="character_knowledge",
        filename="character.md",
        content_type="text/markdown",
        content=b"The pet likes moon tea and quiet libraries.",
        source_label="character sheet",
    )
    await service.ingest(
        collection="user_documents",
        filename="workspace.txt",
        content_type="text/plain",
        content=b"The project uses Godot 4 for desktop rendering.",
    )

    character_results = await service.search(RagSearchRequest(
        collection="character_knowledge",
        query="What does the pet like?",
    ))
    user_results = await service.search(RagSearchRequest(
        collection="user_documents",
        query="Which renderer does this project use?",
    ))

    assert character_results.results[0].document_id == character.document_id
    assert "moon tea" in character_results.results[0].content
    assert "Godot 4" in user_results.results[0].content

    await service.delete("character_knowledge", character.document_id)
    after_delete = await service.search(RagSearchRequest(
        collection="character_knowledge",
        query="What does the pet like?",
    ))
    assert after_delete.results == []


@pytest.mark.asyncio
async def test_rag_service_status_reports_in_memory_store() -> None:
    service = RagService(
        rag_settings(),
        store=InMemoryRagStore(),
        embedder=HashEmbeddingAdapter(128),
    )

    status = await service.health()

    assert status.ok is True
    assert status.collections == {
        "character_knowledge": True,
        "user_documents": True,
    }


def test_milvus_store_creates_explicit_varchar_primary_key_schema() -> None:
    class IndexParams:
        def __init__(self) -> None:
            self.entries: list[dict[str, object]] = []

        def add_index(self, **kwargs: object) -> None:
            self.entries.append(kwargs)

    class Client:
        def __init__(self) -> None:
            self.create_call: dict[str, object] | None = None
            self.index_call: dict[str, object] | None = None
            self.loaded_collection: str | None = None

        def has_collection(self, *, collection_name: str) -> bool:
            assert collection_name == "character_knowledge"
            return False

        def create_collection(self, **kwargs: object) -> None:
            self.create_call = kwargs

        def list_indexes(self, *, collection_name: str) -> list[str]:
            assert collection_name == "character_knowledge"
            return []

        def prepare_index_params(self) -> IndexParams:
            return IndexParams()

        def create_index(self, **kwargs: object) -> None:
            self.index_call = kwargs

        def load_collection(self, *, collection_name: str, timeout: float) -> None:
            assert timeout == 10
            self.loaded_collection = collection_name

    client = Client()
    store = MilvusRagStore("http://unused.test", dimension=384, timeout_seconds=10)
    store._client = client

    store._ensure_collection("character_knowledge")

    assert client.create_call is not None
    schema = client.create_call["schema"]
    fields = {field.name: field for field in schema.fields}
    assert fields["chunk_id"].is_primary is True
    assert fields["chunk_id"].params["max_length"] == CHUNK_ID_MAX_LENGTH
    assert fields["embedding"].params["dim"] == 384
    assert client.index_call is not None
    index_params = client.index_call["index_params"]
    assert index_params.entries == [{
        "field_name": "embedding",
        "index_type": "AUTOINDEX",
        "metric_type": "COSINE",
    }]
    assert client.loaded_collection == "character_knowledge"


@pytest.mark.asyncio
async def test_list_documents_groups_by_document_id() -> None:
    store = InMemoryRagStore()
    service = RagService(rag_settings(), store=store)
    first = await service.ingest(
        "character_knowledge",
        "a.md",
        "text/markdown",
        "# 角色设定\n\n这是一段角色设定内容，用于分组测试，需要足够长。".encode("utf-8"),
    )
    second = await service.ingest(
        "character_knowledge",
        "b.md",
        "text/markdown",
        "# other\n\nA completely different document content for listing.".encode("utf-8"),
    )

    documents = await service.list_documents("character_knowledge")
    ids = {document.document_id for document in documents}
    assert ids == {first.document_id, second.document_id}


@pytest.mark.asyncio
async def test_ingest_same_document_is_deduplicated() -> None:
    store = InMemoryRagStore()
    service = RagService(rag_settings(), store=store)
    content = "# repeat\n\n同一份文档的固定内容，反复上传不应重复写入，需要足够长。".encode("utf-8")
    first = await service.ingest("character_knowledge", "a.md", "text/markdown", content)
    repeat = await service.ingest("character_knowledge", "a-copy.md", "text/markdown", content)

    assert repeat.document_id == first.document_id
    assert repeat.deduplicated is True
    documents = await service.list_documents("character_knowledge")
    assert len(documents) == 1


@pytest.mark.asyncio
async def test_sqlite_vec_store_persists_isolates_and_deletes_documents(tmp_path) -> None:
    database_path = tmp_path / "separate-rag.sqlite3"
    store = SqliteVecRagStore(database_path, dimension=3)

    assert await store.health() == {
        "character_knowledge": False,
        "user_documents": False,
    }

    await store.insert("character_knowledge", [{
        "chunk_id": "11111111-1111-1111-1111-111111111111:0",
        "document_id": "11111111-1111-1111-1111-111111111111",
        "filename": "character.md",
        "source_label": "角色设定",
        "chunk_index": 0,
        "content": "喜欢月见茶和安静的图书馆。",
        "updated_at": 100,
        "content_hash": "hash-character",
        "embedding": [1.0, 0.0, 0.0],
    }])
    await store.insert("user_documents", [{
        "chunk_id": "22222222-2222-2222-2222-222222222222:0",
        "document_id": "22222222-2222-2222-2222-222222222222",
        "filename": "project.txt",
        "source_label": "project.txt",
        "chunk_index": 0,
        "content": "项目使用 Godot 4。",
        "updated_at": 200,
        "content_hash": "hash-project",
        "embedding": [0.0, 1.0, 0.0],
    }])

    character_hits = await store.search("character_knowledge", [1.0, 0.0, 0.0], 5)
    user_hits = await store.search("user_documents", [0.0, 1.0, 0.0], 5)
    assert len(character_hits) == 1
    assert character_hits[0].content == "喜欢月见茶和安静的图书馆。"
    assert character_hits[0].score == pytest.approx(1.0)
    assert user_hits[0].document_id == "22222222-2222-2222-2222-222222222222"
    assert await store.health() == {
        "character_knowledge": True,
        "user_documents": True,
    }
    assert (
        await store.find_document_by_content_hash("character_knowledge", "hash-character")
    ).document_id == "11111111-1111-1111-1111-111111111111"

    await store.close()
    reopened = SqliteVecRagStore(database_path, dimension=3)
    reopened_hits = await reopened.search("character_knowledge", [1.0, 0.0, 0.0], 1)
    assert reopened_hits[0].filename == "character.md"

    await reopened.delete_document(
        "character_knowledge",
        "11111111-1111-1111-1111-111111111111",
    )
    assert await reopened.search("character_knowledge", [1.0, 0.0, 0.0], 1) == []
    assert await reopened.list_documents("character_knowledge") == []
    await reopened.close()


@pytest.mark.asyncio
async def test_rag_service_uses_separate_sqlite_vec_store(tmp_path) -> None:
    service = RagService(sqlite_rag_settings(tmp_path))

    status = await service.health()
    assert status.ok is True
    assert status.store == "sqlite-vec"
    assert status.collections == {
        "character_knowledge": False,
        "user_documents": False,
    }

    document = await service.ingest(
        collection="character_knowledge",
        filename="character.md",
        content_type="text/markdown",
        content=b"The pet likes moon tea and quiet libraries.",
        source_label="character sheet",
    )
    after_ingest = await service.health()
    assert after_ingest.collections["character_knowledge"] is True
    assert after_ingest.collections["user_documents"] is False

    results = await service.search(RagSearchRequest(
        collection="character_knowledge",
        query="What does the pet like?",
    ))
    assert results.results[0].document_id == document.document_id

    repeated = await service.ingest(
        collection="character_knowledge",
        filename="character-copy.md",
        content_type="text/markdown",
        content=b"The pet likes moon tea and quiet libraries.",
    )
    assert repeated.deduplicated is True
    assert repeated.document_id == document.document_id

    documents = await service.list_documents("character_knowledge")
    assert len(documents) == 1
    await service.close()


@pytest.mark.asyncio
async def test_sqlite_vec_store_rejects_dimension_mismatch(tmp_path) -> None:
    store = SqliteVecRagStore(tmp_path / "rag.sqlite3", dimension=3)
    with pytest.raises(RagError) as mismatch:
        await store.search("character_knowledge", [1.0, 0.0], 1)
    assert mismatch.value.code == "INVALID_CONFIG"
    await store.close()
