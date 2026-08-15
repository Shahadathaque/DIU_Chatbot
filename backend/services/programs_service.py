"""Program list service derived from the cleaned DIU knowledge base."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.core.errors import ArtifactUnavailableError
from backend.core.cache import TTLCache
from backend.core.config import get_settings
from backend.models.programs import Program, ProgramsResponse
from backend.repositories.runtime_catalog import (
    RuntimeCatalogError,
    RuntimeCatalogRepository,
)
from rag.chunker import load_cleaned_records
from rag.config import get_rag_settings


def _degree_from_name(name: str) -> Optional[str]:
    for pattern, degree in _DEGREE_RULES:
        if pattern.match(name):
            return degree
    return None
_SLUG_KEEP = re.compile(r"[^a-z0-9]+")
_MAJOR_IN_PATTERN = re.compile(r"^major in\b", re.IGNORECASE)

_PROGRAMS_CACHE: TTLCache[ProgramsResponse] = TTLCache()

# Ordered prefix rules: the first match wins, so specific degrees must precede
# their generic fallbacks (for example "Bachelor of Business Administration"
# before the catch-all "Bachelor of").
_DEGREE_RULES = (
    (re.compile(r"^\s*ll\.?\s?m", re.IGNORECASE), "LL.M."),
    (re.compile(r"^\s*ll\.?\s?b", re.IGNORECASE), "LL.B."),
    (re.compile(r"^\s*m\.?\s?a\b", re.IGNORECASE), "M.A."),
    (re.compile(r"^\s*m\.?\s?sc", re.IGNORECASE), "M.Sc."),
    (re.compile(r"^\s*m\.?\s?pharm", re.IGNORECASE), "M.Pharm"),
    (re.compile(r"^\s*mss\b", re.IGNORECASE), "MSS"),
    (re.compile(r"^\s*master of pharmacy\b", re.IGNORECASE), "M.Pharm"),
    (re.compile(r"^\s*master of public health\b", re.IGNORECASE), "MPH"),
    (re.compile(r"^\s*master of business administration\b", re.IGNORECASE), "MBA"),
    (re.compile(r"^\s*master of development studies\b", re.IGNORECASE), "MDS"),
    (re.compile(r"^\s*master of", re.IGNORECASE), "M."),
    (re.compile(r"^\s*m\.?\s?ba\b", re.IGNORECASE), "MBA"),
    (re.compile(r"^\s*post\s?graduate", re.IGNORECASE), "PGD"),
    (re.compile(r"^\s*b\.?\s?a\b", re.IGNORECASE), "B.A."),
    (re.compile(r"^\s*b\.?\s?sc", re.IGNORECASE), "B.Sc."),
    (re.compile(r"^\s*b\.?\s?arch", re.IGNORECASE), "B.Arch"),
    (re.compile(r"^\s*b\.?\s?pharm", re.IGNORECASE), "B.Pharm"),
    (re.compile(r"^\s*bss\b", re.IGNORECASE), "BSS"),
    (re.compile(r"^\s*bba\b", re.IGNORECASE), "BBA"),
    (re.compile(r"^\s*bachelor of pharmacy\b", re.IGNORECASE), "B.Pharm"),
    (re.compile(r"^\s*bachelor of architecture\b", re.IGNORECASE), "B.Arch"),
    (re.compile(r"^\s*bachelor of public health\b", re.IGNORECASE), "BPH"),
    (re.compile(r"^\s*bachelor of business administration\b", re.IGNORECASE), "BBA"),
    (re.compile(r"^\s*bachelor of", re.IGNORECASE), "B."),
)


def _slug(value: str) -> str:
    return _SLUG_KEEP.sub("-", value.casefold()).strip("-") or "program"


class ProgramsService:
    """Build the program catalog from cleaned records (never typed manually).

    Programs come from ``undergraduate_programs`` table rows and from
    ``program_specific_admission`` records that carry an explicit program name.
    Only fields actually present in the cleaned data are emitted; missing
    optional fields are omitted rather than fabricated.
    """

    def __init__(
        self,
        records: Optional[Iterable[Dict[str, Any]]] = None,
        *,
        cleaned_root: Optional[str] = None,
        repository: Optional[RuntimeCatalogRepository] = None,
        catalog_backend: Optional[str] = None,
    ) -> None:
        self._records = records
        self._cleaned_root = cleaned_root
        self._repository = repository
        self._catalog_backend = catalog_backend
        self._cache_default = (
            records is None
            and cleaned_root is None
            and repository is None
            and catalog_backend is None
        )

    def list_programs(self) -> ProgramsResponse:
        # Injected records are used by tests and callers that intentionally
        # provide a snapshot; only the default cleaned snapshot is cached.
        if self._cache_default:
            cached = _PROGRAMS_CACHE.get()
            if cached is not None:
                return cached
        if self._records is None and self._use_database():
            response = self._list_database_programs()
            if self._cache_default:
                _PROGRAMS_CACHE.set(response)
            return response
        records = list(self._records if self._records is not None else self._load_records())
        programs: List[Program] = []
        for record in records:
            if record.get("category") == "undergraduate_programs":
                programs.extend(self._programs_from_tables(record))
            elif (
                record.get("category") == "program_specific_admission"
                and record.get("program")
            ):
                programs.append(
                    self._program_from_record(record, name=str(record["program"]))
                )
        response = ProgramsResponse(
            programs=self._ensure_unique_ids(
                self._dedupe(programs, records=records)
            ),
        )
        if self._cache_default:
            _PROGRAMS_CACHE.set(response)
        return response

    def _use_database(self) -> bool:
        if self._repository is not None:
            return True
        if self._cleaned_root is not None:
            return False
        backend = self._catalog_backend or get_settings().runtime_catalog_backend
        return backend == "database"

    def _list_database_programs(self) -> ProgramsResponse:
        repository = self._repository
        if repository is None:
            database_url = get_settings().database_url
            if not database_url:
                raise ArtifactUnavailableError(
                    artifact="Neon runtime program catalog",
                    path="diu_runtime_programs",
                    recovery="Configure DATABASE_URL and synchronize the runtime catalog.",
                )
            repository = RuntimeCatalogRepository(database_url)
        try:
            rows = repository.list_programs()
        except RuntimeCatalogError as error:
            raise ArtifactUnavailableError(
                artifact="Neon runtime program catalog",
                path="diu_runtime_programs",
                recovery="Run scripts/sync_runtime_catalog.py and verify Neon connectivity.",
            ) from error
        return ProgramsResponse(programs=[Program.model_validate(row) for row in rows])

    def _load_records(self) -> Sequence[Dict[str, Any]]:
        root = self._cleaned_root or str(get_rag_settings().rag_cleaned_data_path)
        try:
            return load_cleaned_records(root)
        except (OSError, ValueError) as error:
            raise ArtifactUnavailableError(
                artifact="cleaned DIU dataset",
                path=root,
                recovery="Restore the cleaned snapshot or run scripts/clean_dataset.py.",
            ) from error

    @staticmethod
    def _programs_from_tables(record: Dict[str, Any]) -> List[Program]:
        programs: List[Program] = []
        for table in record.get("tables", []):
            headers = [str(item).strip().casefold() for item in table.get("headers", [])]
            if "full program name" not in headers or "short tag / initials" not in headers:
                continue
            name_index = headers.index("full program name")
            tag_index = headers.index("short tag / initials")
            faculty_index = headers.index("faculty") if "faculty" in headers else None
            url_index = headers.index("program page") if "program page" in headers else None
            for row in table.get("rows", []):
                if len(row) <= max(name_index, tag_index):
                    continue
                name = str(row[name_index]).strip()
                tag = str(row[tag_index]).strip()
                if not name:
                    continue
                faculty = None
                if faculty_index is not None and len(row) > faculty_index:
                    faculty = str(row[faculty_index]).strip() or None
                admission_url = None
                if url_index is not None and len(row) > url_index:
                    admission_url = str(row[url_index]).strip() or None
                programs.append(
                    Program(
                        id=_program_id(name, tag),
                        name=name,
                        degree=_degree_from_name(name),
                        faculty=faculty,
                        admission_url=admission_url,
                    )
                )
        return programs

    @staticmethod
    def _program_from_record(record: Dict[str, Any], *, name: str) -> Program:
        return Program(
            id=_slug(name),
            name=name,
            faculty=record.get("faculty") or None,
            admission_url=record.get("source_url") or None,
        )

    @staticmethod
    def _dedupe(
        programs: List[Program], *, records: Sequence[Dict[str, Any]]
    ) -> List[Program]:
        del records  # All merge decisions are made from source-derived program fields.
        seen: Dict[str, Program] = {}
        for program in programs:
            key = program.name.casefold()
            previous = seen.get(key)
            if previous is None:
                seen[key] = program
                continue
            # Merge source-backed optional detail without producing a duplicate.
            updates = {}
            if previous.faculty is None and program.faculty is not None:
                updates["faculty"] = program.faculty
            if previous.admission_url is None and program.admission_url is not None:
                updates["admission_url"] = program.admission_url
            if updates:
                seen[key] = previous.model_copy(update=updates)

        # A program-specific source may use only the official short name (for
        # example "BBA") while the catalog carries the full program name. Merge
        # it only when the stable id identifies exactly one full-name candidate;
        # shared tags such as CSE/SWE remain separate when they are ambiguous.
        values = list(seen.values())
        full_by_id: Dict[str, List[Program]] = {}
        for program in values:
            if program.name.casefold() != program.id.casefold():
                full_by_id.setdefault(program.id, []).append(program)
        aliases_to_remove: set[str] = set()
        for alias in values:
            if alias.name.casefold() != alias.id.casefold():
                continue
            candidates = full_by_id.get(alias.id, [])
            if len(candidates) != 1:
                continue
            target = candidates[0]
            updates = {}
            if target.faculty is None and alias.faculty is not None:
                updates["faculty"] = alias.faculty
            if target.admission_url is None and alias.admission_url is not None:
                updates["admission_url"] = alias.admission_url
            if updates:
                seen[target.name.casefold()] = target.model_copy(update=updates)
            aliases_to_remove.add(alias.name.casefold())
        for key in aliases_to_remove:
            seen.pop(key, None)
        return sorted(seen.values(), key=lambda item: item.name.casefold())

    @staticmethod
    def _ensure_unique_ids(programs: List[Program]) -> List[Program]:
        """Make every program id stable and unique across the response.

        Different programs can legitimately share a short tag (for example the
        SWE family), which previously produced duplicate ids. For any id shared
        by more than one program, disambiguate each program by appending a
        deterministic slug derived from its full name, so the id stays
        meaningful and reproducible without random values or array indexes.
        """
        if not programs:
            return programs
        counts: Dict[str, int] = {}
        for program in programs:
            counts[program.id] = counts.get(program.id, 0) + 1

        used: set[str] = set()
        uniqued: List[Program] = []
        for program in programs:
            program_id = program.id
            if counts[program_id] > 1 and program_id in used:
                name_slug = _slug(program.name) if program.name else program_id
                program_id = f"{program_id}-{name_slug}"
            used.add(program_id)
            uniqued.append(program.model_copy(update={"id": program_id}))
        return uniqued


def _program_id(name: str, tag: str) -> str:
    tag_slug = _slug(tag) if tag else ""
    match = re.search(r"\(([^)]+)\)", name)
    if match:
        spec = _MAJOR_IN_PATTERN.sub("", match.group(1).strip()).strip()
        spec_slug = _slug(spec) if spec else ""
        if spec_slug and spec_slug != tag_slug:
            return f"{tag_slug}-{spec_slug}" if tag_slug else spec_slug
    if tag_slug:
        return tag_slug
    return _slug(name)
