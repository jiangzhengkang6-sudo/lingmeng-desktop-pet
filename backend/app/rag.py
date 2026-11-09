from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import dataclass
from contextlib import contextmanager
from hashlib import blake2b
from math import sqrt
from pathlib import Path
import hashlib
import re
from time import time
from typing import Any, Protocol, Sequence
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import Settings


RAG_COLLECTIONS = frozenset({"character_knowledge", "user_documents"})
SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
SUPPORTED_CONTENT_TYPES = frozenset({"text/plain", "text/markdown"})
OUTPUT_FIELDS = [
    "document_id",
    "filename",
    "source_label",
    "chunk_index",
    "content",
    "updated_at",
]
CHUNK_ID_MAX_LENGTH = 64


class RagError(Exception):
    def __init__(self, message: str, code: str = "RAG_ERROR", status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class RagSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("collection")
    @classmethod
    def validate_collection(cls, value: str) -> str:
        return validate_collection(value)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query cannot be blank")
        return value


class RagDeleteResponse(BaseModel):
    ok: bool = True
    collection: str
    document_id: str


class RagIngestResponse(BaseModel):
    collection: str
    document_id: str
    filename: str
    source_label: str
    chunk_count: int
    updated_at: int
    content_hash: str = ""
    deduplicated: bool = False


class RagSearchHitResponse(BaseModel):
    document_id: str
    filename: str
    source_label: str
    chunk_index: int
    content: str
    updated_at: int
    score: float


class RagSearchResponse(BaseModel):
    collection: str
    results: list[RagSearchHitResponse]


class RagHealthResponse(BaseModel):
    ok: bool
    store: str
    embedding_provider: str
    embedding_model: str
    embedding_configured: bool
    collections: dict[str, bool]
    error: str | None = None


@dataclass(frozen=True)
class DocumentChunk:
    content: str
    chunk_index: int


@dataclass(frozen=True)
class RagSearchHit:
    document_id: str
    filename: str
    source_label: str
    chunk_index: int
    content: str
    updated_at: int
    score: float


class EmbeddingAdapter(Protocol):
    dimension: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class RagStore(Protocol):
    name: str

    async def close(self) -> None: ...

    async def health(self) -> dict[str, bool]: ...

    async def insert(
        self,
        collection: str,
        records: Sequence[dict[str, object]],
    ) -> None: ...

    async def search(
        self,
        collection: str,
        vector: Sequence[float],
        limit: int,
    ) -> list[RagSearchHit]: ...

    async def delete_document(self, collection: str, document_id: str) -> None: ...

    async def list_documents(self, collection: str) -> list[RagIngestResponse]: ...

    async def find_document_by_content_hash(
        self,
        collection: str,
        content_hash: str,
    ) -> RagIngestResponse | None: ...


class HashEmbeddingAdapter:
    """A deterministic local embedder used for offline development and smoke tests."""

    def __init__(self, dimension: int):
        if dimension < 32:
            raise RagError("RAG_EMBEDDING_DIMENSION must be at least 32", "INVALID_CONFIG", 500)
        self.dimension = dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u3400-\u9fff]|[^\s]", text.lower())
        if not tokens:
            return vector
        for token in tokens:
            digest = blake2b(token.encode("utf-8"), digest_size=16).digest()
            for offset in range(0, len(digest), 4):
                value = int.from_bytes(digest[offset:offset + 4], "big")
                index = value % self.dimension
                vector[index] += 1.0 if value & 1 else -1.0
        length = sqrt(sum(value * value for value in vector))
        return [value / length for value in vector] if length else vector


class OpenAiCompatibleEmbeddingAdapter:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.dimension = settings.rag_embedding_dimension
        self.client = client
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.settings.rag_embedding_configured:
            raise RagError("RAG embedding provider is not configured", "NOT_CONFIGURED", 503)
        headers = {
            "Authorization": f"Bearer {self.settings.rag_embedding_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = {"model": self.settings.rag_embedding_model, "input": list(texts)}
        try:
            if self.client is not None:
                response = await self.client.post(
                    self.settings.rag_embedding_endpoint,
                    headers=headers,
                    json=body,
                    timeout=self.settings.rag_timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(trust_env=False) as client:
                    response = await client.post(
                        self.settings.rag_embedding_endpoint,
                        headers=headers,
                        json=body,
                        timeout=self.settings.rag_timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise RagError("RAG embedding request timed out", "TIMEOUT", 504) from exc
        except httpx.HTTPError as exc:
            raise RagError("RAG embedding provider is unavailable", "NETWORK", 502) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RagError("RAG embedding provider returned invalid JSON", "INVALID_RESPONSE", 502) from exc
        if response.status_code >= 400:
            message = payload.get("error") or payload.get("message") or "RAG embedding request failed"
            if isinstance(message, dict):
                message = message.get("message") or "RAG embedding request failed"
            raise RagError(str(message), "PROVIDER_HTTP", 502)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise RagError("RAG embedding provider response is invalid", "INVALID_RESPONSE", 502)

        rows = sorted(payload["data"], key=lambda item: item.get("index", 0))
        vectors: list[list[float]] = []
        for row in rows:
            embedding = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(embedding, list) or not all(isinstance(value, (float, int)) for value in embedding):
                raise RagError("RAG embedding vector is invalid", "INVALID_RESPONSE", 502)
            vector = [float(value) for value in embedding]
            if len(vector) != self.dimension:
                raise RagError(
                    "RAG embedding dimension does not match RAG_EMBEDDING_DIMENSION",
                    "INVALID_RESPONSE",
                    502,
                )
            vectors.append(vector)
        if len(vectors) != len(texts):
            raise RagError("RAG embedding response count is invalid", "INVALID_RESPONSE", 502)
        return vectors


class MilvusRagStore:
    name = "milvus"

    def __init__(self, uri: str, dimension: int, timeout_seconds: float):
        self.uri = uri
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds
        self._client: Any | None = None

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, bool]:
        return await asyncio.to_thread(self._health_sync)

    async def insert(self, collection: str, records: Sequence[dict[str, object]]) -> None:
        await asyncio.to_thread(self._insert_sync, collection, list(records))

    async def search(self, collection: str, vector: Sequence[float], limit: int) -> list[RagSearchHit]:
        return await asyncio.to_thread(self._search_sync, collection, list(vector), limit)

    async def delete_document(self, collection: str, document_id: str) -> None:
        await asyncio.to_thread(self._delete_document_sync, collection, document_id)

    async def list_documents(self, collection: str) -> list[RagIngestResponse]:
        return await asyncio.to_thread(self._list_documents_sync, collection)

    async def find_document_by_content_hash(
        self,
        collection: str,
        content_hash: str,
    ) -> RagIngestResponse | None:
        return await asyncio.to_thread(
            self._find_document_by_content_hash_sync,
            collection,
            content_hash,
        )

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from pymilvus import MilvusClient

            self._client = MilvusClient(uri=self.uri, timeout=self.timeout_seconds)
            return self._client
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Failed to connect Milvus at %s: %s: %s", self.uri, type(exc).__name__, exc)
            raise RagError("Milvus is unavailable", "STORE_UNAVAILABLE", 503) from exc

    def _health_sync(self) -> dict[str, bool]:
        try:
            client = self._client_or_raise()
            return {name: bool(client.has_collection(collection_name=name)) for name in RAG_COLLECTIONS}
        except RagError:
            raise
        except Exception as exc:
            raise RagError("Milvus is unavailable", "STORE_UNAVAILABLE", 503) from exc

    def _ensure_collection(self, collection: str) -> Any:
        client = self._client_or_raise()
        try:
            if not client.has_collection(collection_name=collection):
                from pymilvus import CollectionSchema, DataType, FieldSchema

                schema = CollectionSchema(
                    fields=[
                        FieldSchema(
                            name="chunk_id",
                            dtype=DataType.VARCHAR,
                            is_primary=True,
                            auto_id=False,
                            max_length=CHUNK_ID_MAX_LENGTH,
                        ),
                        FieldSchema(
                            name="embedding",
                            dtype=DataType.FLOAT_VECTOR,
                            dim=self.dimension,
                        ),
                    ],
                    enable_dynamic_field=True,
                )
                client.create_collection(
                    collection_name=collection,
                    schema=schema,
                    metric_type="COSINE",
                    consistency_level="Strong",
                    timeout=self.timeout_seconds,
                )
            if "embedding" not in client.list_indexes(collection_name=collection):
                index_params = client.prepare_index_params()
                index_params.add_index(
                    field_name="embedding",
                    index_type="AUTOINDEX",
                    metric_type="COSINE",
                )
                client.create_index(
                    collection_name=collection,
                    index_params=index_params,
                    timeout=self.timeout_seconds,
                )
            client.load_collection(
                collection_name=collection,
                timeout=self.timeout_seconds,
            )
            return client
        except Exception as exc:
            raise RagError("Milvus collection initialization failed", "STORE_UNAVAILABLE", 503) from exc

    def _insert_sync(self, collection: str, records: list[dict[str, object]]) -> None:
        try:
            client = self._ensure_collection(collection)
            client.insert(collection_name=collection, data=records, timeout=self.timeout_seconds)
        except RagError:
            raise
        except Exception as exc:
            raise RagError("Milvus document insert failed", "STORE_UNAVAILABLE", 503) from exc

    def _search_sync(self, collection: str, vector: list[float], limit: int) -> list[RagSearchHit]:
        try:
            client = self._ensure_collection(collection)
            raw_results = client.search(
                collection_name=collection,
                data=[vector],
                limit=limit,
                output_fields=OUTPUT_FIELDS,
                timeout=self.timeout_seconds,
            )
        except RagError:
            raise
        except Exception as exc:
            raise RagError("Milvus search failed", "STORE_UNAVAILABLE", 503) from exc

        hits = raw_results[0] if raw_results else []
        parsed: list[RagSearchHit] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            entity = hit.get("entity")
            data = entity if isinstance(entity, dict) else hit
            try:
                parsed.append(RagSearchHit(
                    document_id=str(data["document_id"]),
                    filename=str(data["filename"]),
                    source_label=str(data["source_label"]),
                    chunk_index=int(data["chunk_index"]),
                    content=str(data["content"]),
                    updated_at=int(data["updated_at"]),
                    score=float(hit.get("distance", hit.get("score", 0.0))),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return parsed

    def _delete_document_sync(self, collection: str, document_id: str) -> None:
        escaped_document_id = document_id.replace("\\", "\\\\").replace('"', '\\"')
        try:
            client = self._ensure_collection(collection)
            client.delete(
                collection_name=collection,
                filter=f'document_id == "{escaped_document_id}"',
                timeout=self.timeout_seconds,
            )
        except RagError:
            raise
        except Exception as exc:
            raise RagError("Milvus document deletion failed", "STORE_UNAVAILABLE", 503) from exc


    _DOCUMENT_METADATA_FIELDS = [
        "document_id",
        "filename",
        "source_label",
        "chunk_index",
        "updated_at",
        "content_hash",
    ]

    def _list_documents_sync(self, collection: str) -> list[RagIngestResponse]:
        client = self._ensure_collection(collection)
        rows: list[dict[str, object]] = []
        iterator = client.query_iterator(
            collection_name=collection,
            filter="",
            output_fields=self._DOCUMENT_METADATA_FIELDS,
            batch_size=200,
            timeout=self.timeout_seconds,
        )
        try:
            while True:
                batch = iterator.next()
                if not batch:
                    break
                rows.extend(batch)
                if len(rows) >= 1_000:
                    break
        finally:
            iterator.close()
        return self._summarize_rows(collection, rows)

    def _find_document_by_content_hash_sync(
        self,
        collection: str,
        content_hash: str,
    ) -> RagIngestResponse | None:
        client = self._ensure_collection(collection)
        rows = client.query(
            collection_name=collection,
            filter=f'content_hash == "{content_hash}"',
            output_fields=self._DOCUMENT_METADATA_FIELDS,
            limit=100,
            timeout=self.timeout_seconds,
        )
        summaries = self._summarize_rows(collection, rows)
        return summaries[0] if summaries else None

    def _summarize_rows(
        self,
        collection: str,
        rows: Sequence[dict[str, object]],
    ) -> list[RagIngestResponse]:
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            document_id = str(row["document_id"])
            item = grouped.setdefault(document_id, {
                "document_id": document_id,
                "filename": str(row["filename"]),
                "source_label": str(row["source_label"]),
                "chunks": set(),
                "updated_at": 0,
                "content_hash": str(row.get("content_hash") or ""),
            })
            try:
                item["chunks"].add(int(row["chunk_index"]))
            except (TypeError, ValueError):
                item["chunks"].add(len(item["chunks"]))
            item["updated_at"] = max(int(item["updated_at"]), int(row["updated_at"]))
        summaries = [
            RagIngestResponse(
                collection=collection,
                document_id=document_id,
                filename=str(item["filename"]),
                source_label=str(item["source_label"]),
                chunk_count=len(item["chunks"]),
                updated_at=int(item["updated_at"]),
                content_hash=str(item["content_hash"]),
            )
            for document_id, item in grouped.items()
        ]
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return summaries


class SqliteVecRagStore:
    """使用独立 SQLite 文件保存 RAG 元数据和 sqlite-vec 向量。"""

    name = "sqlite-vec"

    def __init__(self, database_path: Path, dimension: int, timeout_seconds: float = 10.0):
        self.database_path = database_path
        self.dimension = dimension
        self.timeout_seconds = max(float(timeout_seconds), 1.0)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    async def health(self) -> dict[str, bool]:
        return await asyncio.to_thread(self._health_sync)

    async def insert(self, collection: str, records: Sequence[dict[str, object]]) -> None:
        await asyncio.to_thread(self._insert_sync, collection, list(records))

    async def search(
        self,
        collection: str,
        vector: Sequence[float],
        limit: int,
    ) -> list[RagSearchHit]:
        return await asyncio.to_thread(self._search_sync, collection, list(vector), limit)

    async def delete_document(self, collection: str, document_id: str) -> None:
        await asyncio.to_thread(self._delete_document_sync, collection, document_id)

    async def list_documents(self, collection: str) -> list[RagIngestResponse]:
        return await asyncio.to_thread(self._list_documents_sync, collection)

    async def find_document_by_content_hash(
        self,
        collection: str,
        content_hash: str,
    ) -> RagIngestResponse | None:
        return await asyncio.to_thread(
            self._find_document_by_content_hash_sync,
            collection,
            content_hash,
        )

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    @contextmanager
    def _locked_connection(self):
        with self._lock:
            yield self._connect_locked()

    def _connect_locked(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        try:
            import sqlite_vec

            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(self.database_path),
                timeout=self.timeout_seconds,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            busy_timeout = int(self.timeout_seconds * 1000)
            connection.execute(f"PRAGMA busy_timeout = {busy_timeout}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.enable_load_extension(True)
            sqlite_vec.load(connection)
            connection.enable_load_extension(False)
            self._initialize_locked(connection)
            self._connection = connection
            return connection
        except RagError:
            raise
        except Exception as exc:
            raise RagError("sqlite-vec is unavailable", "STORE_UNAVAILABLE", 503) from exc

    def _initialize_locked(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                collection TEXT NOT NULL,
                document_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                source_label TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                chunk_count INTEGER NOT NULL CHECK (chunk_count > 0),
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (collection, document_id),
                UNIQUE (collection, content_hash)
            );

            CREATE TABLE IF NOT EXISTS chunks (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,
                document_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                source_label TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE (collection, document_id, chunk_index),
                FOREIGN KEY (collection, document_id)
                    REFERENCES documents(collection, document_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document
                ON chunks(collection, document_id);
            CREATE INDEX IF NOT EXISTS idx_documents_hash
                ON documents(collection, content_hash);
            """
        )
        row = connection.execute(
            "SELECT value FROM rag_metadata WHERE key = 'embedding_dimension'"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO rag_metadata(key, value) VALUES ('embedding_dimension', ?)",
                (str(self.dimension),),
            )
            connection.commit()
        elif int(row["value"]) != self.dimension:
            raise RagError(
                "RAG sqlite embedding dimension does not match the existing database",
                "INVALID_CONFIG",
                500,
            )

    def _health_sync(self) -> dict[str, bool]:
        try:
            import sqlite_vec

            with self._locked_connection() as connection:
                tables = {
                    str(row["name"])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtualname')"
                    )
                }
                return {
                    collection: self._vector_table_name(collection) in tables
                    for collection in RAG_COLLECTIONS
                }
        except RagError:
            raise
        except Exception as exc:
            raise RagError("sqlite-vec is unavailable", "STORE_UNAVAILABLE", 503) from exc

    def _ensure_collection_locked(self, connection: sqlite3.Connection, collection: str) -> str:
        table_name = self._vector_table_name(collection)
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        if exists is None:
            # 表名和维度来自受信枚举与整数配置；向量值仍通过参数绑定。
            connection.execute(
                f"""
                CREATE VIRTUAL TABLE {table_name} USING vec0(
                    chunk_key INTEGER PRIMARY KEY,
                    embedding float[{self.dimension}] distance_metric=cosine
                )
                """
            )
            connection.commit()
        return table_name

    def _insert_sync(self, collection: str, records: list[dict[str, object]]) -> None:
        if not records:
            return
        try:
            import sqlite_vec

            with self._locked_connection() as connection:
                table_name = self._ensure_collection_locked(connection, collection)
                document_ids = {str(record["document_id"]) for record in records}
                if len(document_ids) != 1:
                    raise RagError("RAG records must belong to one document", "INVALID_REQUEST", 400)
                connection.execute("BEGIN IMMEDIATE")
                try:
                    first = records[0]
                    connection.execute(
                        """
                        INSERT INTO documents(
                            collection, document_id, filename, source_label,
                            content_hash, chunk_count, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(collection, document_id) DO UPDATE SET
                            filename=excluded.filename,
                            source_label=excluded.source_label,
                            content_hash=excluded.content_hash,
                            chunk_count=excluded.chunk_count,
                            updated_at=excluded.updated_at
                        """,
                        (
                            collection,
                            str(first["document_id"]),
                            str(first["filename"]),
                            str(first["source_label"]),
                            str(first["content_hash"]),
                            len(records),
                            int(first["updated_at"]),
                        ),
                    )
                    for record in records:
                        embedding = [float(value) for value in record["embedding"]]  # type: ignore[arg-type]
                        if len(embedding) != self.dimension:
                            raise RagError(
                                "RAG embedding dimension does not match sqlite-vec table",
                                "INVALID_CONFIG",
                                500,
                            )
                        cursor = connection.execute(
                            """
                            INSERT INTO chunks(
                                collection, document_id, chunk_id, filename, source_label,
                                chunk_index, content, content_hash, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                collection,
                                str(record["document_id"]),
                                str(record["chunk_id"]),
                                str(record["filename"]),
                                str(record["source_label"]),
                                int(record["chunk_index"]),
                                str(record["content"]),
                                str(record["content_hash"]),
                                int(record["updated_at"]),
                            ),
                        )
                        connection.execute(
                            f"INSERT INTO {table_name}(chunk_key, embedding) VALUES (?, ?)",
                            (cursor.lastrowid, sqlite_vec.serialize_float32(embedding)),
                        )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except RagError:
            raise
        except Exception as exc:
            raise RagError("sqlite-vec document insert failed", "STORE_UNAVAILABLE", 503) from exc

    def _search_sync(
        self,
        collection: str,
        vector: list[float],
        limit: int,
    ) -> list[RagSearchHit]:
        if len(vector) != self.dimension:
            raise RagError(
                "RAG embedding dimension does not match sqlite-vec table",
                "INVALID_CONFIG",
                500,
            )
        try:
            import sqlite_vec

            with self._locked_connection() as connection:
                table_name = self._vector_table_name(collection)
                if connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone() is None:
                    return []
                rows = connection.execute(
                    f"""
                    SELECT
                        c.document_id,
                        c.filename,
                        c.source_label,
                        c.chunk_index,
                        c.content,
                        c.updated_at,
                        v.distance
                    FROM {table_name} v
                    JOIN chunks c ON c.rowid = v.chunk_key
                    WHERE c.collection = ? AND v.embedding MATCH ? AND v.k = ?
                    ORDER BY v.distance
                    """,
                    (collection, sqlite_vec.serialize_float32(vector), int(limit)),
                ).fetchall()
                return [
                    RagSearchHit(
                        document_id=str(row["document_id"]),
                        filename=str(row["filename"]),
                        source_label=str(row["source_label"]),
                        chunk_index=int(row["chunk_index"]),
                        content=str(row["content"]),
                        updated_at=int(row["updated_at"]),
                        score=1.0 - float(row["distance"]),
                    )
                    for row in rows
                ]
        except RagError:
            raise
        except Exception as exc:
            raise RagError("sqlite-vec document search failed", "STORE_UNAVAILABLE", 503) from exc

    def _delete_document_sync(self, collection: str, document_id: str) -> None:
        try:
            with self._locked_connection() as connection:
                table_name = self._vector_table_name(collection)
                vector_table_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone() is not None
                connection.execute("BEGIN IMMEDIATE")
                try:
                    if vector_table_exists:
                        connection.execute(
                            f"""
                            DELETE FROM {table_name}
                            WHERE chunk_key IN (
                                SELECT rowid FROM chunks
                                WHERE collection = ? AND document_id = ?
                            )
                            """,
                            (collection, document_id),
                        )
                    connection.execute(
                        "DELETE FROM chunks WHERE collection = ? AND document_id = ?",
                        (collection, document_id),
                    )
                    connection.execute(
                        "DELETE FROM documents WHERE collection = ? AND document_id = ?",
                        (collection, document_id),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except RagError:
            raise
        except Exception as exc:
            raise RagError("sqlite-vec document deletion failed", "STORE_UNAVAILABLE", 503) from exc

    def _list_documents_sync(self, collection: str) -> list[RagIngestResponse]:
        with self._locked_connection() as connection:
            rows = connection.execute(
                """
                SELECT document_id, filename, source_label, content_hash,
                       chunk_count, updated_at
                FROM documents
                WHERE collection = ?
                ORDER BY updated_at DESC, document_id DESC
                """,
                (collection,),
            ).fetchall()
        return [self._document_from_row(collection, row) for row in rows]

    def _find_document_by_content_hash_sync(
        self,
        collection: str,
        content_hash: str,
    ) -> RagIngestResponse | None:
        with self._locked_connection() as connection:
            row = connection.execute(
                """
                SELECT document_id, filename, source_label, content_hash,
                       chunk_count, updated_at
                FROM documents
                WHERE collection = ? AND content_hash = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (collection, content_hash),
            ).fetchone()
        return self._document_from_row(collection, row) if row is not None else None

    @staticmethod
    def _document_from_row(collection: str, row: sqlite3.Row) -> RagIngestResponse:
        return RagIngestResponse(
            collection=collection,
            document_id=str(row["document_id"]),
            filename=str(row["filename"]),
            source_label=str(row["source_label"]),
            chunk_count=int(row["chunk_count"]),
            updated_at=int(row["updated_at"]),
            content_hash=str(row["content_hash"]),
        )

    def _close_sync(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @staticmethod
    def _vector_table_name(collection: str) -> str:
        validate_collection(collection)
        return f"rag_vec_{collection}"


class InMemoryRagStore:
    """Small test double that mirrors RAG collection isolation."""

    name = "memory"

    def __init__(self):
        self.records: dict[str, list[dict[str, object]]] = {name: [] for name in RAG_COLLECTIONS}

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, bool]:
        return {name: True for name in RAG_COLLECTIONS}

    async def insert(self, collection: str, records: Sequence[dict[str, object]]) -> None:
        self.records[collection].extend(records)

    async def search(self, collection: str, vector: Sequence[float], limit: int) -> list[RagSearchHit]:
        scored: list[tuple[float, dict[str, object]]] = []
        for record in self.records[collection]:
            embedding = record["embedding"]
            score = sum(float(a) * float(b) for a, b in zip(vector, embedding, strict=True))  # type: ignore[arg-type]
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RagSearchHit(
                document_id=str(record["document_id"]),
                filename=str(record["filename"]),
                source_label=str(record["source_label"]),
                chunk_index=int(record["chunk_index"]),
                content=str(record["content"]),
                updated_at=int(record["updated_at"]),
                score=score,
            )
            for score, record in scored[:limit]
        ]

    async def delete_document(self, collection: str, document_id: str) -> None:
        self.records[collection] = [
            record for record in self.records[collection]
            if record["document_id"] != document_id
        ]

    async def list_documents(self, collection: str) -> list[RagIngestResponse]:
        return self._summarize(collection, self.records[collection])

    async def find_document_by_content_hash(
        self,
        collection: str,
        content_hash: str,
    ) -> RagIngestResponse | None:
        matched = [
            record for record in self.records[collection]
            if str(record.get("content_hash") or "") == content_hash
        ]
        summaries = self._summarize(collection, matched)
        return summaries[0] if summaries else None

    def _summarize(
        self,
        collection: str,
        rows: Sequence[dict[str, object]],
    ) -> list[RagIngestResponse]:
        grouped: dict[str, dict[str, object]] = {}
        for record in rows:
            document_id = str(record["document_id"])
            item = grouped.setdefault(document_id, {
                "document_id": document_id,
                "filename": str(record["filename"]),
                "source_label": str(record["source_label"]),
                "chunks": set(),
                "updated_at": 0,
                "content_hash": str(record.get("content_hash") or ""),
            })
            item["chunks"].add(int(record["chunk_index"]))
            item["updated_at"] = max(int(item["updated_at"]), int(record["updated_at"]))
        summaries = [
            RagIngestResponse(
                collection=collection,
                document_id=document_id,
                filename=str(item["filename"]),
                source_label=str(item["source_label"]),
                chunk_count=len(item["chunks"]),
                updated_at=int(item["updated_at"]),
                content_hash=str(item["content_hash"]),
            )
            for document_id, item in grouped.items()
        ]
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return summaries


class RagService:
    def __init__(
        self,
        settings: Settings,
        store: RagStore | None = None,
        embedder: EmbeddingAdapter | None = None,
    ):
        self.settings = settings
        self.embedder = embedder or self._create_embedder(settings)
        self.store = store or self._create_store(settings, self.embedder)
        if not 1 <= settings.rag_chunk_overlap < settings.rag_chunk_size:
            raise RagError("RAG chunk overlap must be smaller than chunk size", "INVALID_CONFIG", 500)

    @staticmethod
    def _create_store(settings: Settings, embedder: EmbeddingAdapter) -> RagStore:
        if settings.rag_store == "sqlite-vec":
            return SqliteVecRagStore(
                database_path=settings.rag_sqlite_path,
                dimension=embedder.dimension,
                timeout_seconds=settings.rag_timeout_seconds,
            )
        if settings.rag_store == "milvus":
            return MilvusRagStore(
                uri=settings.rag_milvus_uri,
                dimension=embedder.dimension,
                timeout_seconds=settings.rag_timeout_seconds,
            )
        raise RagError("RAG_STORE is not supported", "INVALID_CONFIG", 500)

    def _create_embedder(self, settings: Settings) -> EmbeddingAdapter:
        if settings.rag_embedding_provider == "hash":
            return HashEmbeddingAdapter(settings.rag_embedding_dimension)
        if settings.rag_embedding_provider == "openai-compatible":
            return OpenAiCompatibleEmbeddingAdapter(settings)
        raise RagError("RAG_EMBEDDING_PROVIDER is not supported", "INVALID_CONFIG", 500)

    async def close(self) -> None:
        if isinstance(self.embedder, OpenAiCompatibleEmbeddingAdapter):
            await self.embedder.close()
        if isinstance(self.store, SqliteVecRagStore):
            await self.store.close()

    async def health(self) -> RagHealthResponse:
        try:
            collections = await self.store.health()
            return RagHealthResponse(
                ok=True,
                store=self.store.name,
                embedding_provider=self.settings.rag_embedding_provider,
                embedding_model=self.settings.rag_embedding_model,
                embedding_configured=self.settings.rag_embedding_configured,
                collections=collections,
            )
        except RagError as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("RAG store health check failed: %s", exc)
            return RagHealthResponse(
                ok=False,
                store=getattr(self.store, "name", self.settings.rag_store),
                embedding_provider=self.settings.rag_embedding_provider,
                embedding_model=self.settings.rag_embedding_model,
                embedding_configured=self.settings.rag_embedding_configured,
                collections={name: False for name in RAG_COLLECTIONS},
                error=exc.code,
                error_message=str(exc),
            )

    async def ingest(
        self,
        collection: str,
        filename: str,
        content_type: str | None,
        content: bytes,
        source_label: str | None = None,
    ) -> RagIngestResponse:
        collection = validate_collection(collection)
        text = decode_text_document(filename, content_type, content, self.settings.rag_max_upload_bytes)
        content_hash = document_content_hash(text)

        existing = await self.store.find_document_by_content_hash(collection, content_hash)
        if existing is not None:
            return existing.model_copy(update={"deduplicated": True})

        chunks = split_document(text, self.settings.rag_chunk_size, self.settings.rag_chunk_overlap)
        document_id = str(uuid4())
        now = int(time())
        safe_filename = sanitize_filename(filename)
        safe_source_label = sanitize_source_label(source_label) or safe_filename
        embeddings = await self.embedder.embed([chunk.content for chunk in chunks])
        records = [
            {
                "chunk_id": f"{document_id}:{chunk.chunk_index}",
                "document_id": document_id,
                "filename": safe_filename,
                "source_label": safe_source_label,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "updated_at": now,
                "content_hash": content_hash,
                "embedding": embedding,
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        await self.store.insert(collection, records)
        return RagIngestResponse(
            collection=collection,
            document_id=document_id,
            filename=safe_filename,
            source_label=safe_source_label,
            chunk_count=len(chunks),
            updated_at=now,
            content_hash=content_hash,
            deduplicated=False,
        )

    async def list_documents(self, collection: str) -> list[RagIngestResponse]:
        collection = validate_collection(collection)
        return await self.store.list_documents(collection)

    async def search(self, request: RagSearchRequest) -> RagSearchResponse:
        vector = (await self.embedder.embed([request.query]))[0]
        hits = await self.store.search(request.collection, vector, request.limit)
        return RagSearchResponse(
            collection=request.collection,
            results=[RagSearchHitResponse(**hit.__dict__) for hit in hits],
        )

    async def delete(self, collection: str, document_id: str) -> RagDeleteResponse:
        collection = validate_collection(collection)
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", document_id):
            raise RagError("document_id is invalid", "INVALID_REQUEST", 400)
        await self.store.delete_document(collection, document_id)
        return RagDeleteResponse(collection=collection, document_id=document_id)


def validate_collection(value: str) -> str:
    if value not in RAG_COLLECTIONS:
        raise ValueError("collection is not allowed")
    return value


def sanitize_filename(filename: str) -> str:
    value = Path(filename or "document.txt").name.strip()
    value = re.sub(r"[\x00-\x1f]", "", value)
    return value[:255] or "document.txt"


def sanitize_source_label(value: str | None) -> str:
    cleaned = re.sub(r"[\x00-\x1f]", "", (value or "").strip())
    return cleaned[:255]


def decode_text_document(
    filename: str,
    content_type: str | None,
    content: bytes,
    max_bytes: int,
) -> str:
    if len(content) > max_bytes:
        raise RagError("document exceeds RAG_MAX_UPLOAD_BYTES", "PAYLOAD_TOO_LARGE", 413)
    suffix = Path(filename).suffix.lower()
    normalized_content_type = (content_type or "").split(";", 1)[0].lower()
    if suffix not in SUPPORTED_SUFFIXES and normalized_content_type not in SUPPORTED_CONTENT_TYPES:
        raise RagError("only UTF-8 text and Markdown documents are supported", "UNSUPPORTED_DOCUMENT", 415)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RagError("document must be UTF-8 encoded", "UNSUPPORTED_DOCUMENT", 415) from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    if not text:
        raise RagError("document is empty", "INVALID_DOCUMENT", 400)
    return text


def split_document(text: str, chunk_size: int, overlap: int) -> list[DocumentChunk]:
    if chunk_size < 64 or overlap < 0 or overlap >= chunk_size:
        raise RagError("invalid RAG chunk configuration", "INVALID_CONFIG", 500)
    chunks: list[str] = []
    current = ""
    for paragraph in (part.strip() for part in re.split(r"\n{2,}", text) if part.strip()):
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(paragraph, chunk_size, overlap))
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return [DocumentChunk(content=chunk, chunk_index=index) for index, chunk in enumerate(chunks)]


def _split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + chunk_size // 2, end),
                text.rfind(" ", start + chunk_size // 2, end),
                text.rfind("。", start + chunk_size // 2, end),
                text.rfind(".", start + chunk_size // 2, end),
            )
            if boundary > start:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks

def document_content_hash(text: str) -> str:
    normalized = "\n".join(
        line.strip() for line in text.strip().splitlines() if line.strip()
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
