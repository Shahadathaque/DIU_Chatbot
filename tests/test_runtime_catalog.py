"""Runtime catalog derivation and PostgreSQL repository tests."""

from __future__ import annotations

from backend.repositories.runtime_catalog import RuntimeCatalogMetadata
from scripts.sync_runtime_catalog import synchronize_runtime_catalog
from tests.rag_helpers import cleaned_record, write_cleaned_dataset


def test_runtime_catalog_dry_run_derives_rows_with_validated_provenance(tmp_path) -> None:
    program_record = cleaned_record(
        source_id="DIU-PROG-001",
        category="undergraduate_programs",
        title="Official programs",
        tables=[
            {
                "headers": ["Full Program Name", "Short Tag / Initials"],
                "rows": [["B. Sc. in Computer Science and Engineering", "CSE"]],
            }
        ],
    )
    root = write_cleaned_dataset(tmp_path / "cleaned", [program_record])

    report = synchronize_runtime_catalog(cleaned_root=root, dry_run=True)

    assert report["programs"] == 1
    assert report["sources"] == 1
    assert report["synchronized"] is False
    assert len(report["manifest_hash"]) == 64


def test_runtime_catalog_sync_passes_atomic_dataset_to_repository(tmp_path) -> None:
    program_record = cleaned_record(
        source_id="DIU-PROG-001",
        category="undergraduate_programs",
        title="Official programs",
        tables=[
            {
                "headers": ["Full Program Name", "Short Tag / Initials"],
                "rows": [["B. Sc. in Computer Science and Engineering", "CSE"]],
            }
        ],
    )
    root = write_cleaned_dataset(tmp_path / "cleaned", [program_record])

    class CapturingRepository:
        programs = None
        sources = None
        metadata = None

        def synchronize(self, *, programs, sources, metadata):
            self.programs = programs
            self.sources = sources
            self.metadata = metadata

    repository = CapturingRepository()
    report = synchronize_runtime_catalog(
        cleaned_root=root,
        repository=repository,
    )

    assert report["synchronized"] is True
    assert repository.programs[0]["source_id"] == "DIU-PROG-001"
    assert repository.programs[0]["document_hash"] == program_record["cleaned_content_hash"]
    assert repository.sources[0]["content_hash"] == program_record["cleaned_content_hash"]
    assert isinstance(repository.metadata, RuntimeCatalogMetadata)
    assert repository.metadata.program_count == 1
    assert repository.metadata.source_count == 1
