"""Neon/PostgreSQL persistence for the runtime program and source catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence


class RuntimeCatalogError(RuntimeError):
    """Raised when the runtime catalog cannot be read or synchronized."""


@dataclass(frozen=True)
class RuntimeCatalogMetadata:
    """Reproducibility metadata for one synchronized cleaned snapshot."""

    dataset_version: str
    dataset_fingerprint: str
    manifest_hash: str
    program_count: int
    source_count: int


class RuntimeCatalogRepository:
    """Read and atomically replace the small runtime catalog in PostgreSQL."""

    def __init__(self, database_url: str, *, connect_timeout: int = 10) -> None:
        if not database_url or not database_url.strip():
            raise ValueError("DATABASE_URL is required for the database runtime catalog")
        self._database_url = database_url
        self._connect_timeout = connect_timeout

    def list_programs(self) -> list[Dict[str, Any]]:
        """Return API-ready program rows without exposing provenance columns."""

        query = """
            SELECT program_id AS id, name, degree, faculty, admission_url
            FROM diu_runtime_programs
            ORDER BY lower(name), name
        """
        return self._fetch_all(query)

    def list_sources(self) -> list[Dict[str, Any]]:
        """Return API-ready official source rows."""

        query = """
            SELECT source_id AS id, title, source_url AS url,
                   retrieved_at, category
            FROM diu_runtime_sources
            ORDER BY lower(source_id), source_id
        """
        return self._fetch_all(query)

    def metadata(self) -> Optional[Dict[str, Any]]:
        """Return the active runtime dataset metadata, if synchronized."""

        rows = self._fetch_all(
            """
            SELECT dataset_version, dataset_fingerprint, manifest_hash,
                   program_count, source_count, synced_at
            FROM diu_runtime_metadata
            WHERE singleton = TRUE
            """
        )
        return rows[0] if rows else None

    def is_ready(self) -> bool:
        """Check that metadata and the expected number of catalog rows exist."""

        try:
            rows = self._fetch_all(
                """
                SELECT metadata.program_count, metadata.source_count,
                       (SELECT count(*) FROM diu_runtime_programs) AS actual_programs,
                       (SELECT count(*) FROM diu_runtime_sources) AS actual_sources
                FROM diu_runtime_metadata AS metadata
                WHERE metadata.singleton = TRUE
                """
            )
        except RuntimeCatalogError:
            return False
        if not rows:
            return False
        row = rows[0]
        return (
            int(row["program_count"]) > 0
            and int(row["source_count"]) > 0
            and int(row["program_count"]) == int(row["actual_programs"])
            and int(row["source_count"]) == int(row["actual_sources"])
        )

    def synchronize(
        self,
        *,
        programs: Sequence[Mapping[str, Any]],
        sources: Sequence[Mapping[str, Any]],
        metadata: RuntimeCatalogMetadata,
    ) -> None:
        """Atomically replace runtime rows with one validated snapshot."""

        if not programs:
            raise ValueError("refusing to synchronize an empty program catalog")
        if not sources:
            raise ValueError("refusing to synchronize an empty source catalog")
        if metadata.program_count != len(programs):
            raise ValueError("program metadata count does not match input rows")
        if metadata.source_count != len(sources):
            raise ValueError("source metadata count does not match input rows")

        psycopg, dict_row, Jsonb = _load_psycopg()
        try:
            with psycopg.connect(
                self._database_url,
                connect_timeout=self._connect_timeout,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    self._create_schema(cursor)
                    cursor.execute("DELETE FROM diu_runtime_programs")
                    cursor.execute("DELETE FROM diu_runtime_sources")
                    for row in programs:
                        cursor.execute(
                            """
                            INSERT INTO diu_runtime_programs (
                                program_id, name, degree, faculty, admission_url,
                                source_id, source_url, retrieved_at, document_id,
                                document_hash, content_hash, provenance
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            """,
                            (
                                row["id"], row["name"], row.get("degree"),
                                row.get("faculty"), row.get("admission_url"),
                                row["source_id"], row["source_url"],
                                row.get("retrieved_at"), row["document_id"],
                                row["document_hash"], row["content_hash"],
                                Jsonb(dict(row.get("provenance") or {})),
                            ),
                        )
                    for row in sources:
                        cursor.execute(
                            """
                            INSERT INTO diu_runtime_sources (
                                source_id, title, source_url, category,
                                retrieved_at, document_id, document_hash,
                                content_hash, provenance
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                row["id"], row["title"], row["url"],
                                row.get("category"), row.get("retrieved_at"),
                                row["document_id"], row["document_hash"],
                                row["content_hash"],
                                Jsonb(dict(row.get("provenance") or {})),
                            ),
                        )
                    cursor.execute(
                        """
                        INSERT INTO diu_runtime_metadata (
                            singleton, dataset_version, dataset_fingerprint,
                            manifest_hash, program_count, source_count, synced_at
                        ) VALUES (TRUE, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (singleton) DO UPDATE SET
                            dataset_version = EXCLUDED.dataset_version,
                            dataset_fingerprint = EXCLUDED.dataset_fingerprint,
                            manifest_hash = EXCLUDED.manifest_hash,
                            program_count = EXCLUDED.program_count,
                            source_count = EXCLUDED.source_count,
                            synced_at = NOW()
                        """,
                        (
                            metadata.dataset_version,
                            metadata.dataset_fingerprint,
                            metadata.manifest_hash,
                            metadata.program_count,
                            metadata.source_count,
                        ),
                    )
        except Exception as error:
            if isinstance(error, (ValueError, RuntimeCatalogError)):
                raise
            raise RuntimeCatalogError(
                "Could not synchronize the PostgreSQL runtime catalog"
            ) from error

    def _fetch_all(self, query: str) -> list[Dict[str, Any]]:
        psycopg, dict_row, _jsonb = _load_psycopg()
        try:
            with psycopg.connect(
                self._database_url,
                connect_timeout=self._connect_timeout,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as error:
            raise RuntimeCatalogError(
                "Could not read the PostgreSQL runtime catalog"
            ) from error

    @staticmethod
    def _create_schema(cursor: Any) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS diu_runtime_programs (
                program_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                degree TEXT NULL,
                faculty TEXT NULL,
                admission_url TEXT NULL,
                source_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                retrieved_at TEXT NULL,
                document_id TEXT NOT NULL,
                document_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
                synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS diu_runtime_sources (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                category TEXT NULL,
                retrieved_at TEXT NULL,
                document_id TEXT NOT NULL,
                document_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
                synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS diu_runtime_metadata (
                singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                dataset_version TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                program_count INTEGER NOT NULL CHECK (program_count > 0),
                source_count INTEGER NOT NULL CHECK (source_count > 0),
                synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def _load_psycopg() -> tuple[Any, Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as error:  # pragma: no cover - deployment dependency guard
        raise RuntimeCatalogError(
            "psycopg is required for the PostgreSQL runtime catalog"
        ) from error
    return psycopg, dict_row, Jsonb


__all__ = [
    "RuntimeCatalogError",
    "RuntimeCatalogMetadata",
    "RuntimeCatalogRepository",
]
