"""Vector storage backends for the DIU retrieval pipeline.

PostgreSQL with pgvector is the production backend.  The JSON and in-memory
implementations deliberately expose the same small API so chunking, retrieval,
and authority filtering can be tested without a database or model download.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import (
    Any,
    Collection,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    runtime_checkable,
)

from rag.config import RagSettings, get_rag_settings
from rag.models import (
    DEFAULT_CURRENCY_STATUSES,
    IndexReport,
    KnowledgeChunk,
    SearchFilters,
    VectorMatch,
)


SCHEMA_VERSION = 1
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_IMMUTABLE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_PROGRAM_ALIASES = {
    "bba": ("BBA",),
    "cis": (
        "B.Sc. in Computing and Information System (CIS)",
        "B. Sc. in Computing and Information System (CIS)",
    ),
    "cse": (
        "B.Sc. in Computer Science and Engineering",
        "B. Sc. in Computer Science and Engineering",
        "M.Sc. in Computer Science and Engineering (CSE)",
        "M. Sc. in Computer Science and Engineering (CSE)",
    ),
    "itm": (
        "B.Sc. in Information Technology & Management (ITM)",
        "B. Sc. in Information Technology & Management (ITM)",
    ),
    "mct": (
        "B.Sc. in Multimedia & Creative Technology (MCT)",
        "B. Sc. in Multimedia & Creative Technology (MCT)",
    ),
    "rme": (
        "B.Sc. in Robotics and Mechatronics Engineering",
        "B. Sc. in Robotics and Mechatronics Engineering",
    ),
    "swe": (
        "B.Sc. in Software Engineering (SWE)",
        "B. Sc. in Software Engineering (SWE)",
        "M.Sc. in Software Engineering (SWE)",
        "M. Sc. in Software Engineering (SWE)",
    ),
}
_CHUNK_FIELDS = (
    "chunk_id",
    "document_id",
    "source_id",
    "source_url",
    "title",
    "category",
    "program",
    "faculty",
    "content",
    "content_type",
    "source_content_type",
    "currency_status",
    "date_sensitive",
    "manual_review",
    "retrieved_at",
    "document_hash",
    "source_hash",
    "content_hash",
    "source_locator",
    "page_number",
    "chunk_index",
    "extraction_status",
    "quality_flags",
)


class VectorStoreError(RuntimeError):
    """Base error for vector-store failures."""


class VectorStoreConfigurationError(VectorStoreError):
    """Raised when a store and its configured embedding model disagree."""


class VectorStoreDependencyError(VectorStoreError):
    """Raised when optional production database dependencies are unavailable."""


@runtime_checkable
class VectorStore(Protocol):
    """Storage contract used by the knowledge-base builder and retriever."""

    embedding_dimension: int
    embedding_model_name: str
    embedding_model_revision: Optional[str]

    def setup(self, *, rebuild: bool = False) -> None:
        """Prepare storage, optionally replacing an existing index."""

        ...

    def upsert_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
        *,
        processed_document_ids: Optional[Collection[str]] = None,
        rebuild: bool = False,
    ) -> IndexReport:
        """Insert/update chunks and remove stale chunks for processed documents."""

        ...

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[SearchFilters] = None,
    ) -> List[VectorMatch]:
        """Return cosine-similar chunks after authority and metadata filters."""

        ...

    def count(self) -> int:
        """Return the number of indexed chunks."""

        ...


class PgVectorStore:
    """Production PostgreSQL + pgvector chunk store using psycopg 3."""

    def __init__(
        self,
        database_url: str,
        *,
        table_name: str = "diu_knowledge_chunks",
        embedding_dimension: int,
        embedding_model_name: str,
        embedding_model_revision: Optional[str] = None,
        require_immutable_revision: bool = True,
        pool_min_size: int = 1,
        pool_max_size: int = 4,
        pool_timeout: float = 10.0,
    ) -> None:
        if not database_url or not database_url.strip():
            raise VectorStoreConfigurationError("DATABASE_URL is required for pgvector")
        self.database_url = database_url
        self.table_name = _validated_identifier(table_name)
        self.metadata_table_name = _validated_metadata_identifier(table_name)
        self.embedding_dimension = _validated_dimension(embedding_dimension)
        self.embedding_model_name = _validated_model_name(embedding_model_name)
        self.embedding_model_revision = _validated_pgvector_revision(
            embedding_model_revision,
            required=require_immutable_revision,
        )
        if pool_min_size < 1 or pool_max_size < pool_min_size:
            raise VectorStoreConfigurationError(
                "database pool sizes must satisfy 1 <= min_size <= max_size"
            )
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.pool_timeout = pool_timeout
        self._pool: Any = None
        self._ready = False

    def setup(self, *, rebuild: bool = False) -> None:
        """Create the extension, schema, metadata row, and search indexes."""

        psycopg, sql, dict_row, _jsonb, _vector, register_vector = (
            _load_pg_dependencies()
        )
        try:
            with self._connection(psycopg, dict_row) as connection:
                self._setup_connection(
                    connection,
                    rebuild=rebuild,
                    sql=sql,
                    register_vector=register_vector,
                )
            self._ready = True
        except VectorStoreError:
            self._ready = False
            raise
        except Exception as error:
            self._ready = False
            raise VectorStoreError(
                "Could not set up PostgreSQL/pgvector storage: {}".format(error)
            ) from error

    def _setup_connection(
        self,
        connection: Any,
        *,
        rebuild: bool,
        sql: Any,
        register_vector: Any,
    ) -> None:
        """Prepare schema inside the caller's active PostgreSQL transaction."""

        table = sql.Identifier(self.table_name)
        metadata_table = sql.Identifier(self.metadata_table_name)
        dimension = sql.SQL(str(self.embedding_dimension))
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            register_vector(connection)
            if rebuild:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(table)
                )
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(metadata_table)
                )

            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                        schema_version INTEGER NOT NULL,
                        embedding_dimension INTEGER NOT NULL,
                        embedding_model_name TEXT NOT NULL,
                        embedding_model_revision TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                ).format(metadata_table)
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        program TEXT NULL,
                        faculty TEXT NULL,
                        content TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        source_content_type TEXT NOT NULL,
                        currency_status TEXT NOT NULL,
                        date_sensitive BOOLEAN NOT NULL,
                        manual_review BOOLEAN NOT NULL,
                        retrieved_at TEXT NOT NULL,
                        document_hash TEXT NOT NULL,
                        source_hash TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        source_locator TEXT NOT NULL,
                        page_number INTEGER NULL,
                        chunk_index INTEGER NOT NULL,
                        extraction_status TEXT NOT NULL,
                        quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
                        embedding_model_name TEXT NOT NULL,
                        embedding_model_revision TEXT NULL,
                        embedding_dimension INTEGER NOT NULL,
                        embedding vector({}) NOT NULL,
                        indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                ).format(table, dimension)
            )
            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (
                        singleton,
                        schema_version,
                        embedding_dimension,
                        embedding_model_name,
                        embedding_model_revision
                    )
                    VALUES (TRUE, %s, %s, %s, %s)
                    ON CONFLICT (singleton) DO NOTHING
                    """
                ).format(metadata_table),
                (
                    SCHEMA_VERSION,
                    self.embedding_dimension,
                    self.embedding_model_name,
                    self.embedding_model_revision,
                ),
            )
            cursor.execute(
                sql.SQL(
                    """
                    SELECT schema_version, embedding_dimension,
                           embedding_model_name, embedding_model_revision
                    FROM {}
                    WHERE singleton = TRUE
                    """
                ).format(metadata_table)
            )
            self._validate_database_metadata(cursor.fetchone())
            cursor.execute(
                """
                SELECT format_type(attribute.atttypid, attribute.atttypmod)
                    AS vector_type
                FROM pg_attribute AS attribute
                WHERE attribute.attrelid = %s::regclass
                  AND attribute.attname = 'embedding'
                  AND NOT attribute.attisdropped
                """,
                (self.table_name,),
            )
            vector_row = cursor.fetchone()
            expected_type = "vector({})".format(self.embedding_dimension)
            if not vector_row or vector_row["vector_type"] != expected_type:
                actual = vector_row["vector_type"] if vector_row else "missing"
                raise VectorStoreConfigurationError(
                    "{} embedding column is {!r}; expected {!r}. Use "
                    "rebuild=True to recreate the RAG index.".format(
                        self.table_name, actual, expected_type
                    )
                )
            self._create_indexes(cursor, sql, table)

    def upsert_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
        *,
        processed_document_ids: Optional[Collection[str]] = None,
        rebuild: bool = False,
        replace_all: bool = False,
    ) -> IndexReport:
        """Upsert chunks atomically and delete stale rows after validation.

        ``replace_all`` is reserved for a complete, non-empty candidate snapshot.
        It removes rows absent from that snapshot inside the same transaction.
        """

        prepared = _prepare_batch(
            chunks,
            embeddings,
            dimension=self.embedding_dimension,
            processed_document_ids=processed_document_ids,
        )
        if not rebuild:
            self._ensure_setup()
        if replace_all and not prepared.entries:
            raise ValueError("refusing to replace the index with an empty snapshot")

        psycopg, sql, dict_row, Jsonb, Vector, register_vector = (
            _load_pg_dependencies()
        )
        try:
            with self._connection(psycopg, dict_row) as connection:
                if rebuild:
                    self._setup_connection(
                        connection,
                        rebuild=True,
                        sql=sql,
                        register_vector=register_vector,
                    )
                else:
                    register_vector(connection)
                report = self.upsert_chunks_on_connection(
                    connection,
                    chunks=chunks,
                    embeddings=embeddings,
                    processed_document_ids=processed_document_ids,
                    replace_all=replace_all,
                    dependencies=(sql, Jsonb, Vector),
                )
            self._ready = True
        except VectorStoreError:
            raise
        except Exception as error:
            raise VectorStoreError(
                "Could not update PostgreSQL/pgvector chunks: {}".format(error)
            ) from error

        return report

    def upsert_chunks_on_connection(
        self,
        connection: Any,
        *,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
        processed_document_ids: Optional[Collection[str]] = None,
        replace_all: bool = False,
        dependencies: Optional[Tuple[Any, Any, Any]] = None,
    ) -> IndexReport:
        """Publish chunks inside a caller-owned PostgreSQL transaction."""

        prepared = _prepare_batch(
            chunks,
            embeddings,
            dimension=self.embedding_dimension,
            processed_document_ids=processed_document_ids,
        )
        if replace_all and not prepared.entries:
            raise ValueError("refusing to replace the index with an empty snapshot")
        if dependencies is None:
            _psycopg, sql, _dict_row, Jsonb, Vector, register_vector = (
                _load_pg_dependencies()
            )
            register_vector(connection)
        else:
            sql, Jsonb, Vector = dependencies
        table = sql.Identifier(self.table_name)
        incoming_ids = [chunk.chunk_id for chunk, _embedding in prepared.entries]
        existing_ids: Set[str] = set()
        inserted = 0
        updated = 0
        deleted = 0
        with connection.cursor() as cursor:
            if incoming_ids:
                cursor.execute(
                    sql.SQL("SELECT chunk_id FROM {} WHERE chunk_id = ANY(%s)").format(
                        table
                    ),
                    (incoming_ids,),
                )
                existing_ids = {row["chunk_id"] for row in cursor.fetchall()}

            statement = self._upsert_statement(sql, table)
            for chunk, embedding in prepared.entries:
                values = _chunk_values(chunk)
                values.extend(
                    [
                        self.embedding_model_name,
                        self.embedding_model_revision,
                        self.embedding_dimension,
                        Vector(embedding),
                    ]
                )
                values[_CHUNK_FIELDS.index("quality_flags")] = Jsonb(
                    list(chunk.quality_flags)
                )
                cursor.execute(statement, values)
                if cursor.fetchone() is None:
                    continue
                if chunk.chunk_id in existing_ids:
                    updated += 1
                else:
                    inserted += 1

            if replace_all:
                cursor.execute(
                    sql.SQL("DELETE FROM {} WHERE NOT (chunk_id = ANY(%s))").format(
                        table
                    ),
                    (incoming_ids,),
                )
                deleted = cursor.rowcount
            elif prepared.processed_document_ids:
                if incoming_ids:
                    cursor.execute(
                        sql.SQL(
                            "DELETE FROM {} WHERE document_id = ANY(%s) "
                            "AND NOT (chunk_id = ANY(%s))"
                        ).format(table),
                        (list(prepared.processed_document_ids), incoming_ids),
                    )
                else:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE document_id = ANY(%s)").format(
                            table
                        ),
                        (list(prepared.processed_document_ids),),
                    )
                deleted = cursor.rowcount
            cursor.execute(sql.SQL("SELECT COUNT(*) AS count FROM {}").format(table))
            total = int(cursor.fetchone()["count"])

        return IndexReport(
            received_chunks=len(prepared.entries),
            inserted_chunks=inserted,
            updated_chunks=updated,
            deleted_stale_chunks=deleted,
            total_chunks=total,
            processed_documents=len(prepared.processed_document_ids),
        )

    def embedding_inventory(self) -> Dict[str, Tuple[str, List[float]]]:
        """Return reusable vectors keyed by stable chunk ID and content hash."""

        self._ensure_setup()
        psycopg, sql, dict_row, _jsonb, _vector, register_vector = (
            _load_pg_dependencies()
        )
        table = sql.Identifier(self.table_name)
        try:
            with self._connection(psycopg, dict_row) as connection:
                register_vector(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT chunk_id, content_hash, embedding FROM {}"
                        ).format(table)
                    )
                    rows = cursor.fetchall()
            return {
                str(row["chunk_id"]): (
                    str(row["content_hash"]),
                    _validated_embedding(row["embedding"], self.embedding_dimension),
                )
                for row in rows
            }
        except VectorStoreError:
            raise
        except Exception as error:
            raise VectorStoreError(
                "Could not read PostgreSQL/pgvector embedding inventory: {}".format(
                    error
                )
            ) from error

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[SearchFilters] = None,
    ) -> List[VectorMatch]:
        """Search eligible rows with pgvector cosine distance."""

        self._ensure_setup()
        query = _validated_embedding(query_embedding, self.embedding_dimension)
        limit = _validated_top_k(top_k)
        resolved_filters = filters or SearchFilters()
        psycopg, sql, dict_row, _jsonb, Vector, register_vector = (
            _load_pg_dependencies()
        )
        table = sql.Identifier(self.table_name)
        where_sql, parameters = _pg_filter_clause(resolved_filters, sql)
        fields = sql.SQL(", ").join(sql.Identifier(field) for field in _CHUNK_FIELDS)
        statement = sql.SQL(
            """
            SELECT {}, 1 - (embedding <=> %s) AS similarity_score
            FROM {}
            WHERE {}
            ORDER BY embedding <=> %s, chunk_id ASC
            LIMIT %s
            """
        ).format(fields, table, where_sql)
        vector = Vector(query)
        try:
            with self._connection(psycopg, dict_row) as connection:
                register_vector(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        statement,
                        [vector] + parameters + [vector, limit],
                    )
                    rows = cursor.fetchall()
        except Exception as error:
            raise VectorStoreError(
                "Could not search PostgreSQL/pgvector chunks: {}".format(error)
            ) from error
        return [
            VectorMatch(
                chunk=_chunk_from_mapping(row),
                similarity_score=float(row["similarity_score"]),
            )
            for row in rows
        ]

    def count(self) -> int:
        """Return the current PostgreSQL row count."""

        self._ensure_setup()
        psycopg, sql, dict_row, _jsonb, _vector, register_vector = (
            _load_pg_dependencies()
        )
        try:
            with self._connection(psycopg, dict_row) as connection:
                register_vector(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) AS count FROM {}").format(
                            sql.Identifier(self.table_name)
                        )
                    )
                    return int(cursor.fetchone()["count"])
        except Exception as error:
            raise VectorStoreError(
                "Could not count PostgreSQL/pgvector chunks: {}".format(error)
            ) from error

    def is_ready(self) -> bool:
        """Read-only compatibility and non-empty check for readiness probes."""

        psycopg, sql, dict_row, _jsonb, _vector, _register_vector = (
            _load_pg_dependencies()
        )
        try:
            with self._connection(psycopg, dict_row) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL(
                            "SELECT schema_version, embedding_dimension, "
                            "embedding_model_name, embedding_model_revision "
                            "FROM {} WHERE singleton = TRUE"
                        ).format(sql.Identifier(self.metadata_table_name))
                    )
                    self._validate_database_metadata(cursor.fetchone())
                    cursor.execute(
                        "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
                        "AS vector_type FROM pg_attribute AS attribute "
                        "WHERE attribute.attrelid = %s::regclass "
                        "AND attribute.attname = 'embedding' "
                        "AND NOT attribute.attisdropped",
                        (self.table_name,),
                    )
                    row = cursor.fetchone()
                    if not row or row["vector_type"] != "vector({})".format(
                        self.embedding_dimension
                    ):
                        return False
                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) AS count FROM {}").format(
                            sql.Identifier(self.table_name)
                        )
                    )
                    return int(cursor.fetchone()["count"]) > 0
        except Exception:
            return False

    def _ensure_setup(self) -> None:
        if not self._ready:
            self.setup()

    def _connection(self, psycopg: Any, dict_row: Any) -> Any:
        """Return a pooled connection when psycopg_pool is installed.

        A direct connection remains the safe development/test fallback. The
        deployment requirements include the pool extra so Neon/pgvector does
        not pay connection setup cost for every retrieval request.
        """

        try:
            from psycopg_pool import ConnectionPool
        except ImportError:
            return psycopg.connect(self.database_url, row_factory=dict_row)
        if self._pool is None:
            self._pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
                timeout=self.pool_timeout,
                kwargs={"row_factory": dict_row},
                open=True,
            )
        return self._pool.connection()

    def close(self) -> None:
        """Close the optional pool during graceful process shutdown."""

        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def _validate_database_metadata(self, metadata: Optional[Dict[str, Any]]) -> None:
        if metadata is None:
            raise VectorStoreConfigurationError("RAG metadata row is missing")
        expected = {
            "schema_version": SCHEMA_VERSION,
            "embedding_dimension": self.embedding_dimension,
            "embedding_model_name": self.embedding_model_name,
            "embedding_model_revision": self.embedding_model_revision,
        }
        mismatches = [
            "{}={!r} (expected {!r})".format(key, metadata.get(key), value)
            for key, value in expected.items()
            if metadata.get(key) != value
        ]
        if mismatches:
            raise VectorStoreConfigurationError(
                "Existing RAG index is incompatible: {}. Use rebuild=True only "
                "when replacing the complete index.".format(", ".join(mismatches))
            )

    def _create_indexes(self, cursor: Any, sql: Any, table: Any) -> None:
        cursor.execute(
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {} ON {} "
                "USING hnsw (embedding vector_cosine_ops)"
            ).format(
                sql.Identifier(_index_name(self.table_name, "embedding_hnsw")),
                table,
            )
        )
        for suffix, columns in (
            ("document_idx", ("document_id",)),
            ("source_idx", ("source_id",)),
            ("category_program_idx", ("category", "program")),
            (
                "authority_idx",
                ("extraction_status", "manual_review", "currency_status"),
            ),
        ):
            cursor.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
                    sql.Identifier(_index_name(self.table_name, suffix)),
                    table,
                    sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                )
            )

    def _upsert_statement(self, sql: Any, table: Any) -> Any:
        stored_fields = _CHUNK_FIELDS + (
            "embedding_model_name",
            "embedding_model_revision",
            "embedding_dimension",
            "embedding",
        )
        columns = sql.SQL(", ").join(sql.Identifier(field) for field in stored_fields)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in stored_fields)
        mutable_fields = tuple(field for field in stored_fields if field != "chunk_id")
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(
                sql.Identifier(field), sql.Identifier(field)
            )
            for field in mutable_fields
        )
        differences = sql.SQL(" OR ").join(
            sql.SQL("{}.{} IS DISTINCT FROM EXCLUDED.{}").format(
                table, sql.Identifier(field), sql.Identifier(field)
            )
            for field in mutable_fields
        )
        return sql.SQL(
            """
            INSERT INTO {} ({}) VALUES ({})
            ON CONFLICT (chunk_id) DO UPDATE SET {}, indexed_at = NOW()
            WHERE {}
            RETURNING chunk_id
            """
        ).format(table, columns, placeholders, assignments, differences)


class InMemoryVectorStore:
    """Process-local implementation useful for focused unit tests."""

    def __init__(
        self,
        *,
        embedding_dimension: int,
        embedding_model_name: str,
        embedding_model_revision: Optional[str] = None,
    ) -> None:
        self.embedding_dimension = _validated_dimension(embedding_dimension)
        self.embedding_model_name = _validated_model_name(embedding_model_name)
        self.embedding_model_revision = embedding_model_revision
        self._entries: Dict[str, Tuple[KnowledgeChunk, List[float]]] = {}
        self._lock = threading.RLock()

    def setup(self, *, rebuild: bool = False) -> None:
        if rebuild:
            with self._lock:
                self._entries.clear()

    def upsert_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
        *,
        processed_document_ids: Optional[Collection[str]] = None,
        rebuild: bool = False,
    ) -> IndexReport:
        prepared = _prepare_batch(
            chunks,
            embeddings,
            dimension=self.embedding_dimension,
            processed_document_ids=processed_document_ids,
        )
        return self._apply_prepared_batch(prepared, rebuild=rebuild)

    def _apply_prepared_batch(
        self, prepared: "_PreparedBatch", *, rebuild: bool
    ) -> IndexReport:
        """Apply an already validated batch while holding the store lock."""

        with self._lock:
            if rebuild:
                self._entries.clear()
            inserted = 0
            updated = 0
            for chunk, embedding in prepared.entries:
                previous = self._entries.get(chunk.chunk_id)
                replacement = (chunk, embedding)
                if previous is None:
                    inserted += 1
                elif previous != replacement:
                    updated += 1
                self._entries[chunk.chunk_id] = replacement

            incoming_ids = {chunk.chunk_id for chunk, _ in prepared.entries}
            stale_ids = [
                chunk_id
                for chunk_id, (chunk, _embedding) in self._entries.items()
                if chunk.document_id in prepared.processed_document_ids
                and chunk_id not in incoming_ids
            ]
            for chunk_id in stale_ids:
                del self._entries[chunk_id]
            total = len(self._entries)

            return IndexReport(
                received_chunks=len(prepared.entries),
                inserted_chunks=inserted,
                updated_chunks=updated,
                deleted_stale_chunks=len(stale_ids),
                total_chunks=total,
                processed_documents=len(prepared.processed_document_ids),
            )

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[SearchFilters] = None,
    ) -> List[VectorMatch]:
        query = _validated_embedding(query_embedding, self.embedding_dimension)
        limit = _validated_top_k(top_k)
        resolved_filters = filters or SearchFilters()
        with self._lock:
            candidates = list(self._entries.values())
        matches = [
            VectorMatch(chunk=chunk, similarity_score=_cosine_similarity(query, vector))
            for chunk, vector in candidates
            if _chunk_is_eligible(chunk, resolved_filters)
        ]
        matches.sort(key=lambda match: (-match.similarity_score, match.chunk.chunk_id))
        return matches[:limit]

    def count(self) -> int:
        with self._lock:
            return len(self._entries)


class LocalVectorStore(InMemoryVectorStore):
    """Small JSON-backed development store; not intended for production use."""

    def __init__(
        self,
        path: Path,
        *,
        embedding_dimension: int,
        embedding_model_name: str,
        embedding_model_revision: Optional[str] = None,
    ) -> None:
        super().__init__(
            embedding_dimension=embedding_dimension,
            embedding_model_name=embedding_model_name,
            embedding_model_revision=embedding_model_revision,
        )
        self.path = Path(path)
        self._loaded = False

    def setup(self, *, rebuild: bool = False) -> None:
        with self._lock:
            if rebuild:
                self._entries.clear()
                self._loaded = True
                self._write_file()
                return
            if self._loaded:
                return
            if not self.path.exists():
                self._entries.clear()
                self._loaded = True
                self._write_file()
                return
            self._load_file()
            self._loaded = True

    def upsert_chunks(
        self,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
        *,
        processed_document_ids: Optional[Collection[str]] = None,
        rebuild: bool = False,
    ) -> IndexReport:
        prepared = _prepare_batch(
            chunks,
            embeddings,
            dimension=self.embedding_dimension,
            processed_document_ids=processed_document_ids,
        )
        with self._lock:
            if not rebuild:
                self.setup()
            previous_entries = self._entries.copy()
            previous_loaded = self._loaded
            try:
                report = self._apply_prepared_batch(prepared, rebuild=rebuild)
                self._loaded = True
                self._write_file()
                return report
            except Exception:
                self._entries = previous_entries
                self._loaded = previous_loaded
                raise

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[SearchFilters] = None,
    ) -> List[VectorMatch]:
        self.setup()
        return super().search(query_embedding, top_k=top_k, filters=filters)

    def count(self) -> int:
        self.setup()
        return super().count()

    def _load_file(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise VectorStoreError(
                "Could not read local vector store {}: {}".format(self.path, error)
            ) from error
        expected = {
            "schema_version": SCHEMA_VERSION,
            "embedding_dimension": self.embedding_dimension,
            "embedding_model_name": self.embedding_model_name,
            "embedding_model_revision": self.embedding_model_revision,
        }
        mismatches = [
            "{}={!r} (expected {!r})".format(key, payload.get(key), value)
            for key, value in expected.items()
            if payload.get(key) != value
        ]
        if mismatches:
            raise VectorStoreConfigurationError(
                "Local RAG index is incompatible: {}. Rebuild the local index."
                .format(", ".join(mismatches))
            )
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise VectorStoreError("Local vector store entries must be a list")
        loaded: Dict[str, Tuple[KnowledgeChunk, List[float]]] = {}
        try:
            for raw_entry in raw_entries:
                chunk = KnowledgeChunk.from_dict(raw_entry["chunk"])
                embedding = _validated_embedding(
                    raw_entry["embedding"], self.embedding_dimension
                )
                if chunk.chunk_id in loaded:
                    raise VectorStoreError(
                        "Duplicate chunk_id in local vector store: {}".format(
                            chunk.chunk_id
                        )
                    )
                loaded[chunk.chunk_id] = (chunk, embedding)
        except (KeyError, TypeError, ValueError) as error:
            raise VectorStoreError(
                "Local vector store contains an invalid entry: {}".format(error)
            ) from error
        self._entries = loaded

    def _write_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "embedding_dimension": self.embedding_dimension,
            "embedding_model_name": self.embedding_model_name,
            "embedding_model_revision": self.embedding_model_revision,
            "entries": [
                {"chunk": chunk.to_dict(), "embedding": embedding}
                for chunk, embedding in (
                    self._entries[chunk_id] for chunk_id in sorted(self._entries)
                )
            ],
        }
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=".{}-".format(self.path.name),
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary_path), str(self.path))
        except OSError as error:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
            raise VectorStoreError(
                "Could not write local vector store {}: {}".format(self.path, error)
            ) from error


def create_vector_store(settings: Optional[RagSettings] = None) -> VectorStore:
    """Construct the configured backend without opening it or loading a model."""

    resolved = settings or get_rag_settings()
    common = {
        "embedding_dimension": resolved.embedding_dimension,
        "embedding_model_name": resolved.embedding_model_name,
        "embedding_model_revision": resolved.embedding_model_revision,
    }
    if resolved.rag_vector_backend == "local":
        return LocalVectorStore(resolved.rag_local_store_path, **common)
    if not resolved.database_url:
        raise VectorStoreConfigurationError(
            "DATABASE_URL is required when RAG_VECTOR_BACKEND=pgvector"
        )
    require_immutable_revision = resolved.embedding_backend == "local"
    common["embedding_model_revision"] = _validated_pgvector_revision(
        resolved.embedding_model_revision,
        required=require_immutable_revision,
    )
    return PgVectorStore(
        resolved.database_url,
        table_name=resolved.rag_table_name,
        require_immutable_revision=require_immutable_revision,
        pool_min_size=resolved.db_pool_min_size,
        pool_max_size=resolved.db_pool_max_size,
        pool_timeout=resolved.db_pool_timeout,
        **common,
    )


class _PreparedBatch:
    def __init__(
        self,
        entries: List[Tuple[KnowledgeChunk, List[float]]],
        processed_document_ids: Set[str],
    ) -> None:
        self.entries = entries
        self.processed_document_ids = processed_document_ids


def _prepare_batch(
    chunks: Sequence[KnowledgeChunk],
    embeddings: Sequence[Sequence[float]],
    *,
    dimension: int,
    processed_document_ids: Optional[Collection[str]],
) -> _PreparedBatch:
    if len(chunks) != len(embeddings):
        raise ValueError(
            "chunks and embeddings must have the same length ({} != {})".format(
                len(chunks), len(embeddings)
            )
        )
    seen_ids: Set[str] = set()
    entries: List[Tuple[KnowledgeChunk, List[float]]] = []
    for chunk, embedding in zip(chunks, embeddings):
        if not isinstance(chunk, KnowledgeChunk):
            raise TypeError("chunks must contain KnowledgeChunk instances")
        if not chunk.chunk_id:
            raise ValueError("chunk_id cannot be empty")
        if not chunk.document_id:
            raise ValueError("document_id cannot be empty")
        if chunk.chunk_id in seen_ids:
            raise ValueError("duplicate input chunk_id: {}".format(chunk.chunk_id))
        seen_ids.add(chunk.chunk_id)
        entries.append((chunk, _validated_embedding(embedding, dimension)))

    chunk_documents = {chunk.document_id for chunk, _embedding in entries}
    if processed_document_ids is None:
        processed = set(chunk_documents)
    else:
        processed = set(processed_document_ids)
        if any(not value for value in processed):
            raise ValueError("processed_document_ids cannot contain empty values")
        missing = chunk_documents - processed
        if missing:
            raise ValueError(
                "processed_document_ids omits input document(s): {}".format(
                    ", ".join(sorted(missing))
                )
            )
    return _PreparedBatch(entries, processed)


def _chunk_values(chunk: KnowledgeChunk) -> List[Any]:
    value = chunk.to_dict()
    return [value[field] for field in _CHUNK_FIELDS]


def _chunk_from_mapping(row: Dict[str, Any]) -> KnowledgeChunk:
    return KnowledgeChunk.from_dict({field: row[field] for field in _CHUNK_FIELDS})


def _chunk_is_eligible(chunk: KnowledgeChunk, filters: SearchFilters) -> bool:
    allowed_statuses = set(DEFAULT_CURRENCY_STATUSES)
    if filters.include_historical:
        allowed_statuses.add("historical")
    if filters.include_uncertain:
        allowed_statuses.add("uncertain")
    if chunk.currency_status not in allowed_statuses:
        return False
    if chunk.manual_review and not filters.include_manual_review:
        return False
    allowed_extraction = {"success", "partial"} if filters.include_partial else {"success"}
    if chunk.extraction_status not in allowed_extraction:
        return False
    if filters.category is not None and (
        chunk.category.casefold() != filters.category.casefold()
    ):
        return False
    if filters.program is not None:
        allowed_programs = _program_filter_values(filters.program)
        if chunk.program is None or chunk.program.casefold() not in allowed_programs:
            return False
    return True


def _pg_filter_clause(filters: SearchFilters, sql: Any) -> Tuple[Any, List[Any]]:
    allowed_statuses = sorted(DEFAULT_CURRENCY_STATUSES)
    if filters.include_historical:
        allowed_statuses.append("historical")
    if filters.include_uncertain:
        allowed_statuses.append("uncertain")
    clauses = [sql.SQL("currency_status = ANY(%s)")]
    parameters: List[Any] = [allowed_statuses]
    if not filters.include_manual_review:
        clauses.append(sql.SQL("manual_review = FALSE"))
    if filters.include_partial:
        clauses.append(sql.SQL("extraction_status = ANY(%s)"))
        parameters.append(["success", "partial"])
    else:
        clauses.append(sql.SQL("extraction_status = 'success'"))
    if filters.category is not None:
        clauses.append(sql.SQL("LOWER(category) = LOWER(%s)"))
        parameters.append(filters.category)
    if filters.program is not None:
        clauses.append(sql.SQL("LOWER(program) = ANY(%s)"))
        parameters.append(list(_program_filter_values(filters.program)))
    return sql.SQL(" AND ").join(clauses), parameters


def _program_filter_values(value: str) -> Tuple[str, ...]:
    """Return case-folded exact labels for a conservative DIU program alias."""

    candidate = value.strip()
    values = [candidate]
    values.extend(_PROGRAM_ALIASES.get(candidate.casefold(), ()))
    return tuple(dict.fromkeys(item.casefold() for item in values))


def _validated_embedding(value: Sequence[float], dimension: int) -> List[float]:
    if isinstance(value, (str, bytes)):
        raise TypeError("embedding must be a numeric sequence")
    try:
        embedding = [float(component) for component in value]
    except (TypeError, ValueError) as error:
        raise ValueError("embedding contains a non-numeric value") from error
    if len(embedding) != dimension:
        raise ValueError(
            "embedding has dimension {}; expected {}".format(
                len(embedding), dimension
            )
        )
    if not all(math.isfinite(component) for component in embedding):
        raise ValueError("embedding values must be finite")
    if not any(component != 0.0 for component in embedding):
        raise ValueError("embedding cannot be the zero vector")
    return embedding


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm)


def _validated_top_k(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("top_k must be a positive integer")
    return value


def _validated_dimension(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise VectorStoreConfigurationError(
            "embedding_dimension must be a positive integer"
        )
    return value


def _validated_model_name(value: str) -> str:
    if not value or not value.strip():
        raise VectorStoreConfigurationError("embedding_model_name cannot be empty")
    return value.strip()


def _validated_identifier(value: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value or ""):
        raise VectorStoreConfigurationError(
            "table_name must start with a lowercase letter, contain only lowercase "
            "letters, digits, and underscores, and be at most 48 characters"
        )
    return value


def _validated_pgvector_revision(
    value: Optional[str], *, required: bool = True
) -> Optional[str]:
    """Validate local commits while allowing provider-versioned hosted models."""

    candidate = value if isinstance(value, str) else ""
    if not candidate and not required:
        return None
    if not _IMMUTABLE_REVISION_PATTERN.fullmatch(candidate):
        raise VectorStoreConfigurationError(
            "EMBEDDING_MODEL_REVISION must be an immutable 40-character "
            "lowercase hexadecimal commit for local pgvector embeddings"
        )
    return candidate


def _validated_metadata_identifier(table_name: str) -> str:
    value = "{}_metadata".format(_validated_identifier(table_name))
    if len(value) > 63:
        raise VectorStoreConfigurationError("derived metadata table name is too long")
    return value


def _index_name(table_name: str, suffix: str) -> str:
    candidate = "{}_{}".format(table_name, suffix)
    if len(candidate) <= 63:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:8]
    return "{}_{}".format(candidate[:54], digest)


@lru_cache(maxsize=1)
def _load_pg_dependencies() -> Tuple[Any, Any, Any, Any, Any, Any]:
    try:
        import psycopg
        from pgvector import Vector
        from pgvector.psycopg import register_vector
        from psycopg import sql
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as error:
        raise VectorStoreDependencyError(
            "PostgreSQL storage requires psycopg[binary] and pgvector. "
            "Install the pinned project requirements."
        ) from error
    return psycopg, sql, dict_row, Jsonb, Vector, register_vector
