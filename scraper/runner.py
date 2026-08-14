"""Run orchestration for controlled, registry-only DIU collection."""

from __future__ import annotations

import logging
import math
import platform
import re
import subprocess
import sys
import time
from importlib import metadata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from scraper.exceptions import FetchError, RegistryError, ScraperError
from scraper.models import SourceRecord
from scraper.registry import load_registry
from scraper.storage import RawStore
from scraper.utils import canonicalize_url, sha256_bytes, sha256_text, utc_now_iso


COLLECTOR_VERSION = "phase4.1-1.0"
LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWED_HOST_SUFFIXES = ("daffodilvarsity.edu.bd",)
DATASET_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class RunConfig:
    """Configuration recorded with every controlled collection run."""

    registry_path: Path = PROJECT_ROOT / "data/source_registry.csv"
    output_root: Path = PROJECT_ROOT / "data/raw"
    project_root: Path = PROJECT_ROOT
    allowed_host_suffixes: Sequence[str] = DEFAULT_ALLOWED_HOST_SUFFIXES
    source_ids: Sequence[str] = ()
    categories: Sequence[str] = ()
    priorities: Sequence[str] = ()
    urls: Sequence[str] = ()
    limit: Optional[int] = None
    skip_existing: bool = False
    dry_run: bool = False
    minimum_delay_seconds: float = 2.0
    maximum_delay_seconds: float = 5.0
    random_seed: int = 20260812
    connect_timeout_seconds: float = 10.0
    request_timeout_seconds: float = 30.0
    playwright_timeout_ms: int = 30_000
    max_retries: int = 2
    dataset_version: Optional[str] = None
    debug: bool = False

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 0:
            raise ValueError("limit must be non-negative")
        if not math.isfinite(self.minimum_delay_seconds) or self.minimum_delay_seconds < 0:
            raise ValueError("minimum delay must be non-negative")
        if (
            not math.isfinite(self.maximum_delay_seconds)
            or self.maximum_delay_seconds < self.minimum_delay_seconds
        ):
            raise ValueError("maximum delay cannot be smaller than minimum delay")
        if not math.isfinite(self.connect_timeout_seconds) or self.connect_timeout_seconds <= 0:
            raise ValueError("connect timeout must be positive and finite")
        if not math.isfinite(self.request_timeout_seconds) or self.request_timeout_seconds <= 0:
            raise ValueError("request timeout must be positive and finite")
        if self.playwright_timeout_ms <= 0:
            raise ValueError("Playwright timeout must be positive")
        if self.max_retries < 0 or self.max_retries > 5:
            raise ValueError("max retries must be between 0 and 5")
        if not self.allowed_host_suffixes:
            raise ValueError("at least one authoritative host suffix is required")
        if self.dataset_version is not None and not DATASET_VERSION_PATTERN.fullmatch(
            self.dataset_version
        ):
            raise ValueError(
                "dataset version must contain only letters, digits, dots, underscores, and hyphens"
            )


@dataclass
class RunSummary:
    """Serializable measured outcome of a dry or collection run."""

    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    selected: int = 0
    attempted: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    html: int = 0
    dynamic: int = 0
    pdf: int = 0
    binary: int = 0
    dry_run: bool = False
    results: List[Dict[str, Any]] = field(default_factory=list)
    robots_reviews: List[Dict[str, Any]] = field(default_factory=list)
    manifest_path: Optional[str] = None
    log_path: Optional[str] = None
    raw_dataset_version: Optional[str] = None
    dataset_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def select_sources(config: RunConfig) -> List[SourceRecord]:
    """Load the validated registry and apply CLI filters."""

    sources = load_registry(
        config.registry_path,
        source_id=config.source_ids or None,
        category=config.categories or None,
        priority=config.priorities or None,
        url=config.urls or None,
        limit=config.limit,
    )
    sources = [
        source
        for source in sources
        if source.scrape_status in {"active", "manual_review"}
    ]
    if not sources:
        raise RegistryError("No registry sources matched the requested filters")
    for source in sources:
        for boundary_url in (source.url, *source.approved_dependency_urls):
            host = (urlsplit(boundary_url).hostname or "").casefold()
            if not any(
                host == suffix.casefold()
                or host.endswith("." + suffix.casefold())
                for suffix in config.allowed_host_suffixes
            ):
                raise RegistryError(
                    f"Source {source.source_id} declares a URL outside the "
                    "authoritative DIU host boundary"
                )
    return sources


def run_collection(config: RunConfig) -> RunSummary:
    """Process registered sources sequentially; isolate every source failure."""

    started_at = utc_now_iso()
    run_id = _run_id(started_at)
    sources = select_sources(config)
    summary = RunSummary(
        run_id=run_id,
        started_at=started_at,
        selected=len(sources),
        dry_run=config.dry_run,
        raw_dataset_version=config.dataset_version,
    )
    store = RawStore(config.output_root)

    if config.dry_run:
        for source in sources:
            already_collected = store.has_successful_capture(source.document_id)
            action = (
                "would_skip"
                if config.skip_existing and already_collected
                else "would_process"
            )
            if action == "would_skip":
                summary.skipped += 1
            summary.results.append(_selection_entry(source, action))
        summary.completed_at = utc_now_iso()
        return summary

    run_log_path = store.log_path(run_id)
    configure_run_logging(run_log_path, debug=config.debug)
    summary.log_path = run_log_path.relative_to(config.output_root).as_posix()

    # Network dependencies are imported only for a real run, allowing a dry run
    # to validate registry selection before environment setup or browser install.
    from scraper.fetcher import (
        DEFAULT_USER_AGENT,
        ROBOTS_USER_AGENT,
        FetchConfig,
        fetch_source,
    )
    from scraper.policy import RobotsChecker
    from scraper.rate_limit import HostRateLimiter

    limiter = HostRateLimiter(
        config.minimum_delay_seconds,
        config.maximum_delay_seconds,
        config.random_seed,
    )
    before_request = lambda url: limiter.wait(url)
    after_request = lambda url: limiter.mark(url)
    fetch_config = FetchConfig(
        user_agent=DEFAULT_USER_AGENT,
        connect_timeout_seconds=config.connect_timeout_seconds,
        request_timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
        retry_backoff_seconds=config.minimum_delay_seconds,
        max_retry_delay_seconds=max(
            config.maximum_delay_seconds, config.minimum_delay_seconds
        ),
        playwright_timeout_ms=config.playwright_timeout_ms,
        before_attempt=before_request,
        after_attempt=after_request,
    )
    robots = RobotsChecker(
        user_agent=ROBOTS_USER_AGENT,
        timeout_seconds=config.request_timeout_seconds,
    )
    robots.before_request = before_request
    robots.after_request = after_request

    store.prepare()
    try:
        for source in sources:
            if config.skip_existing and store.has_successful_capture(source.document_id):
                summary.skipped += 1
                summary.results.append(_selection_entry(source, "skipped_existing"))
                LOGGER.info("SKIP %s (existing document capture)", source.source_id)
                continue

            summary.attempted += 1
            attempted_at = utc_now_iso()
            expected_method = _expected_fetch_method(source)
            LOGGER.info("FETCH %s via %s", source.source_id, expected_method)

            try:
                for policy_url in (source.url, *source.approved_dependency_urls):
                    review = robots.review(policy_url)
                    if not review.allowed:
                        scope = (
                            "source"
                            if policy_url == source.url
                            else "declared browser dependency"
                        )
                        raise FetchError(
                            f"Collection stopped because {scope} robots guidance was "
                            f"{review.outcome}",
                            url=policy_url,
                            method=expected_method,
                        )
                result = fetch_source(source, fetch_config)
                retrieved_at = utc_now_iso()
                extracted = _extract(result)
                content_kind = _content_kind(result, source)
                content_hash = sha256_bytes(result.body)
                record = _success_record(
                    source=source,
                    result=result,
                    extracted=extracted,
                    attempted_at=attempted_at,
                    retrieved_at=retrieved_at,
                    run_id=run_id,
                    content_kind=content_kind,
                    content_hash=content_hash,
                    dataset_version=config.dataset_version,
                )
                outcome = store.store_success(
                    document_id=source.document_id,
                    content_hash=content_hash,
                    raw_bytes=result.body,
                    content_kind=content_kind,
                    record=record,
                )
                summary.successful += 1
                setattr(summary, content_kind, getattr(summary, content_kind) + 1)
                if result.fetch_method == "playwright":
                    summary.dynamic += 1
                summary.results.append(
                    {
                        "source_id": source.source_id,
                        "document_id": source.document_id,
                        "source_url": source.url,
                        "status": "successful",
                        "attempted_at": attempted_at,
                        "retrieved_at": retrieved_at,
                        "fetch_method": result.fetch_method,
                        "http_status": result.status_code,
                        "content_type": content_kind,
                        "content_hash": content_hash,
                        "raw_path": outcome.raw_path,
                        "record_path": outcome.record_path,
                        "duplicate_content": outcome.duplicate_content,
                        "duplicate_record": outcome.duplicate_record,
                        "attempts": result.attempts,
                        "browser_version": result.browser_version,
                        "approved_dependency_urls": list(
                            result.approved_dependency_urls
                        ),
                        "observed_dependency_urls": list(
                            result.observed_dependency_urls
                        ),
                        "redactions": list(result.redactions),
                        "materialized_shadow_roots": result.materialized_shadow_roots,
                        "scrape_status": source.scrape_status,
                        "currency_status": source.currency_status,
                    }
                )
                LOGGER.info(
                    "OK %s HTTP %s %s bytes=%s",
                    source.source_id,
                    result.status_code,
                    content_kind,
                    len(result.body),
                )
            except Exception as error:  # isolate a failed registered source
                retrieved_at = utc_now_iso()
                failure = _failure_record(
                    source=source,
                    error=error,
                    attempted_at=attempted_at,
                    retrieved_at=retrieved_at,
                    run_id=run_id,
                    expected_method=expected_method,
                    dataset_version=config.dataset_version,
                )
                failure_path = None
                try:
                    failure_path = store.store_failure(
                        run_id=run_id,
                        document_id=source.document_id,
                        failure=failure,
                    )
                except Exception as storage_error:
                    LOGGER.error(
                        "Could not persist failure for %s: %s",
                        source.source_id,
                        _concise_message(storage_error),
                    )
                summary.failed += 1
                summary.results.append(
                    {
                        "source_id": source.source_id,
                        "document_id": source.document_id,
                        "source_url": source.url,
                        "status": "failed",
                        "attempted_at": attempted_at,
                        "retrieved_at": retrieved_at,
                        "fetch_method": failure["fetch_method"],
                        "http_status": failure["http_status"],
                        "error_type": failure["error_type"],
                        "error_message": failure["error_message"],
                        "failure_path": failure_path,
                        "attempts": failure["attempts"],
                    }
                )
                if config.debug:
                    LOGGER.exception(
                        "FAIL %s %s: %s",
                        source.source_id,
                        failure["error_type"],
                        failure["error_message"],
                    )
                else:
                    LOGGER.error(
                        "FAIL %s %s: %s",
                        source.source_id,
                        failure["error_type"],
                        failure["error_message"],
                    )
    finally:
        summary.robots_reviews = [
            review.to_dict() for review in robots.reviews.values()
        ]
        robots.close()

    summary.completed_at = utc_now_iso()
    summary.dataset_status = _dataset_status(summary, sources)
    manifest = _manifest(config, summary)
    summary.manifest_path = store.store_manifest(run_id=run_id, manifest=manifest)
    return summary


def configure_run_logging(log_path: Path, *, debug: bool = False) -> None:
    """Configure concise console output plus a per-run-compatible file log."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_path, mode="x", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    root.addHandler(file_handler)


def _extract(result: Any) -> Any:
    from scraper.extractor import ExtractedContent, extract_fetch_result

    try:
        return extract_fetch_result(result)
    except Exception as error:
        return ExtractedContent(
            text=None,
            title=None,
            extraction_method="none",
            warnings=(
                "Lightweight extraction failed; immutable raw bytes were preserved: "
                + _concise_message(error),
            ),
        )


def _content_kind(result: Any, source: SourceRecord) -> str:
    mime_type = (result.mime_type or "").lower()
    prefix = result.body[:1024].lstrip().lower()
    if source.is_pdf or b"%pdf-" in result.body[:1024].lower():
        return "pdf"
    if (
        result.rendered
        or "html" in mime_type
        or prefix.startswith(b"<!doctype html")
        or prefix.startswith(b"<html")
    ):
        return "html"
    return "binary"


def _success_record(
    *,
    source: SourceRecord,
    result: Any,
    extracted: Any,
    attempted_at: str,
    retrieved_at: str,
    run_id: str,
    content_kind: str,
    content_hash: str,
    dataset_version: Optional[str],
) -> Dict[str, Any]:
    content = extracted.text
    return {
        "document_id": source.document_id,
        "source_id": source.source_id,
        "source_url": source.url,
        "canonical_url": source.canonical_url,
        "final_url": _safe_observed_url(source.url, result.final_url),
        "title": source.page_title,
        "observed_title": extracted.title,
        "category": source.category,
        "program": source.program,
        "faculty": source.faculty,
        "priority": source.priority,
        "dynamic_page": source.dynamic_page,
        "date_sensitive": source.date_sensitive,
        "currency_status": source.currency_status,
        "scrape_status": source.scrape_status,
        "source_last_checked": source.last_checked,
        "source_notes": source.notes,
        "approved_dependency_urls": list(source.approved_dependency_urls),
        "observed_dependency_urls": list(result.observed_dependency_urls),
        "dependency_responses": dict(result.dependency_responses),
        "capture_redactions": list(result.redactions),
        "materialized_shadow_roots": result.materialized_shadow_roots,
        "registry_extras": source.extras,
        "retrieved_at": retrieved_at,
        "attempted_at": attempted_at,
        "run_id": run_id,
        "collector_version": COLLECTOR_VERSION,
        "raw_dataset_version": dataset_version,
        "content_type": content_kind,
        "mime_type": result.mime_type,
        "fetch_method": result.fetch_method,
        "rendered": result.rendered,
        "capture_representation": (
            "rendered_dom" if result.rendered else "http_response_entity_bytes"
        ),
        "content": content,
        "content_hash": content_hash,
        "raw_content_hash": content_hash,
        "extracted_content_hash": sha256_text(content) if content is not None else None,
        "hash_algorithm": "sha256",
        "http_status": result.status_code,
        "response_bytes": len(result.body),
        "response_headers": _safe_headers(result.headers),
        "redirect_chain": [
            safe_url
            for value in result.redirect_chain
            if (safe_url := _safe_observed_url(source.url, value)) is not None
        ],
        "attempts": result.attempts,
        "blocked_third_party_origins": list(result.blocked_origins),
        "browser_version": result.browser_version,
        "extraction": {
            "method": extracted.extraction_method,
            "page_count": extracted.page_count,
            "warnings": list(extracted.warnings),
        },
    }


def _failure_record(
    *,
    source: SourceRecord,
    error: Exception,
    attempted_at: str,
    retrieved_at: str,
    run_id: str,
    expected_method: str,
    dataset_version: Optional[str],
) -> Dict[str, Any]:
    return {
        "document_id": source.document_id,
        "source_id": source.source_id,
        "source_url": source.url,
        "canonical_url": source.canonical_url,
        "title": source.page_title,
        "category": source.category,
        "program": source.program,
        "faculty": source.faculty,
        "retrieved_at": retrieved_at,
        "attempted_at": attempted_at,
        "run_id": run_id,
        "collector_version": COLLECTOR_VERSION,
        "raw_dataset_version": dataset_version,
        "currency_status": source.currency_status,
        "scrape_status": source.scrape_status,
        "approved_dependency_urls": list(source.approved_dependency_urls),
        "fetch_method": getattr(error, "method", None) or expected_method,
        "http_status": getattr(error, "status_code", None),
        "error_type": type(error).__name__,
        "error_message": _concise_message(error),
        "attempts": getattr(error, "attempts", 1),
        "final_url": _safe_observed_url(
            source.url, getattr(error, "final_url", None)
        ),
        "redirect_chain": [
            safe_url
            for value in getattr(error, "redirect_chain", ())
            if (safe_url := _safe_observed_url(source.url, value)) is not None
        ],
    }


def _safe_headers(headers: Dict[str, str]) -> Dict[str, str]:
    allowed = {
        "cache-control",
        "content-disposition",
        "content-encoding",
        "content-language",
        "content-length",
        "content-type",
        "date",
        "etag",
        "last-modified",
    }
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


def _safe_observed_url(registered_url: str, value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        canonical = canonicalize_url(str(value))
    except Exception:
        return None
    return canonical if canonical == canonicalize_url(registered_url) else None


def _selection_entry(source: SourceRecord, status: str) -> Dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_url": source.url,
        "title": source.page_title,
        "category": source.category,
        "priority": source.priority,
        "dynamic_page": source.dynamic_page,
        "currency_status": source.currency_status,
        "scrape_status": source.scrape_status,
        "approved_dependency_urls": list(source.approved_dependency_urls),
        "content_type": "pdf" if source.is_pdf else "html",
        "fetch_method": _expected_fetch_method(source),
        "status": status,
    }


def _expected_fetch_method(source: SourceRecord) -> str:
    if source.is_pdf:
        return "requests_pdf"
    return "playwright" if source.dynamic_page else "requests"


def _manifest(config: RunConfig, summary: RunSummary) -> Dict[str, Any]:
    registry_bytes = config.registry_path.read_bytes()
    project_root = config.project_root
    requirements_path = project_root / "requirements.txt"
    return {
        "raw_dataset_version": config.dataset_version,
        "dataset_status": summary.dataset_status,
        "collector_version": COLLECTOR_VERSION,
        "code_revision": _git_revision(project_root),
        "code_worktree_dirty": _git_worktree_dirty(project_root),
        "collector_tree_hash": _collector_tree_hash(project_root),
        "registry_path": _portable_path(config.registry_path, project_root),
        "registry_hash": sha256_bytes(registry_bytes),
        "requirements_path": (
            _portable_path(requirements_path, project_root)
            if requirements_path.is_file()
            else None
        ),
        "requirements_hash": (
            sha256_bytes(requirements_path.read_bytes())
            if requirements_path.is_file()
            else None
        ),
        "hash_algorithm": "sha256",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": _package_versions(
                "beautifulsoup4", "playwright", "requests", "pypdf"
            ),
        },
        "configuration": {
            "source_ids": list(config.source_ids),
            "categories": list(config.categories),
            "priorities": list(config.priorities),
            "urls": list(config.urls),
            "limit": config.limit,
            "skip_existing": config.skip_existing,
            "minimum_delay_seconds": config.minimum_delay_seconds,
            "maximum_delay_seconds": config.maximum_delay_seconds,
            "random_seed": config.random_seed,
            "connect_timeout_seconds": config.connect_timeout_seconds,
            "request_timeout_seconds": config.request_timeout_seconds,
            "playwright_timeout_ms": config.playwright_timeout_ms,
            "max_retries": config.max_retries,
            "dataset_version": config.dataset_version,
            "retry_backoff_seconds": config.minimum_delay_seconds,
            "max_retry_delay_seconds": max(
                config.maximum_delay_seconds, config.minimum_delay_seconds
            ),
            "max_redirects": 0,
            "max_response_bytes": 50 * 1024 * 1024,
            "playwright_network_idle_timeout_ms": 5_000,
            "playwright_settle_ms": 500,
            "verify_tls": True,
            "http_user_agent": (
                "DIU-Admission-Research-Collector/1.0 Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/139.0 Safari/537.36 "
            ),
            "robots_user_agent": "DIU-Admission-Research-Collector",
            "allowed_host_suffixes": list(config.allowed_host_suffixes),
            "debug": config.debug,
            "concurrency": 1,
        },
        "run": {key: value for key, value in summary.to_dict().items() if key != "manifest_path"},
    }


def _dataset_status(
    summary: RunSummary, sources: Sequence[SourceRecord] = ()
) -> str:
    unresolved = any(source.scrape_status == "manual_review" for source in sources)
    if (
        not unresolved
        and summary.failed == 0
        and summary.successful + summary.skipped == summary.selected
    ):
        return "complete"
    if summary.successful > 0:
        return "partial"
    return "incomplete"


def _git_revision(project_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _git_worktree_dirty(project_root: Path) -> Optional[bool]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())


def _package_versions(*package_names: str) -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for package_name in package_names:
        try:
            versions[package_name] = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            versions[package_name] = None
    return versions


def _collector_tree_hash(project_root: Path) -> str:
    """Hash current collector source bytes, including uncommitted work."""

    paths = sorted((project_root / "scraper").glob("*.py"))
    paths.append(project_root / "scripts/scrape_diu.py")
    digest_parts = []
    for path in paths:
        if path.is_file():
            relative = path.relative_to(project_root).as_posix()
            digest_parts.append(relative.encode("utf-8") + b"\0" + path.read_bytes())
    return sha256_bytes(b"\0\0".join(digest_parts))


def _portable_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _run_id(timestamp: str) -> str:
    return (
        "run-"
        + timestamp.replace("-", "").replace(":", "").replace(".", "").replace("Z", "")
    )


def _concise_message(error: BaseException, limit: int = 500) -> str:
    message = " ".join(str(error).split()) or type(error).__name__
    return message if len(message) <= limit else message[: limit - 1] + "…"


__all__ = [
    "COLLECTOR_VERSION",
    "RunConfig",
    "RunSummary",
    "configure_run_logging",
    "run_collection",
    "select_sources",
]
