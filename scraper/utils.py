"""Deterministic, side-effect-free helpers for raw source collection."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import posixpath
import re
import unicodedata
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from scraper.exceptions import InvalidURLError


_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
_TRACKING_QUERY_KEYS = frozenset(
    {
        "_ga",
        "_gl",
        "dclid",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "msclkid",
    }
)
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def sha256_bytes(content: bytes | bytearray | memoryview) -> str:
    """Return the lowercase SHA-256 digest of the exact supplied bytes."""

    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise TypeError("content must be bytes-like")
    return hashlib.sha256(bytes(content)).hexdigest()


def sha256_text(content: str, *, encoding: str = "utf-8") -> str:
    """Return a SHA-256 digest for text encoded deterministically as UTF-8."""

    if not isinstance(content, str):
        raise TypeError("content must be a string")
    return sha256_bytes(content.encode(encoding))


def _normalize_percent_encoding(value: str) -> str:
    """Normalize escapes without turning an escaped slash into a path separator."""

    normalized: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "%" and index + 2 < len(value):
            pair = value[index + 1 : index + 3]
            if all(digit in "0123456789abcdefABCDEF" for digit in pair):
                decoded = chr(int(pair, 16))
                normalized.append(decoded if decoded in _UNRESERVED else f"%{pair.upper()}")
                index += 3
                continue
        if character == "%":
            normalized.append("%25")
        else:
            normalized.append(character)
        index += 1
    return "".join(normalized)


def _normalize_path(path: str) -> str:
    path = _normalize_percent_encoding(path or "/")
    path = re.sub(r"/{2,}", "/", path)
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path
    if path != "/":
        path = path.rstrip("/")
    # Preserve valid URL escapes while encoding spaces, non-ASCII characters, and
    # URL delimiters that belong to the path rather than the query/fragment.
    return quote(path, safe="/%:@-._~!$&'()*+,;=")


def _is_irrelevant_query_key(key: str) -> bool:
    lowered = key.casefold()
    return lowered.startswith("utm_") or lowered in _TRACKING_QUERY_KEYS


def canonicalize_url(url: str) -> str:
    """Return a stable canonical HTTP(S) URL for registry comparisons.

    The protocol calls for normalized scheme, host, path, and irrelevant query
    parameters. This implementation lowercases scheme/host, removes default ports,
    resolves dot and duplicate path segments, removes fragments and common tracking
    parameters, then sorts the remaining query pairs. Meaningful query parameters
    (for example ``?app=home`` in the DIU registry) are retained.
    """

    if not isinstance(url, str) or not url.strip():
        raise InvalidURLError("URL must be a non-empty string", field="url")

    value = url.strip()
    if any(ord(character) < 32 for character in value):
        raise InvalidURLError("URL contains a control character", field="url")

    try:
        parts = urlsplit(value)
        scheme = parts.scheme.casefold()
        hostname = parts.hostname
        port = parts.port
    except ValueError as error:
        raise InvalidURLError(f"invalid URL: {error}", field="url") from error

    if scheme not in {"http", "https"}:
        raise InvalidURLError("URL scheme must be http or https", field="url")
    if not hostname:
        raise InvalidURLError("URL must include a host", field="url")
    if parts.username is not None or parts.password is not None:
        raise InvalidURLError("URL must not include credentials", field="url")

    try:
        ascii_host = hostname.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise InvalidURLError("URL contains an invalid host", field="url") from error
    if not ascii_host or any(character.isspace() for character in ascii_host):
        raise InvalidURLError("URL contains an invalid host", field="url")

    display_host = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    is_default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = display_host if port is None or is_default_port else f"{display_host}:{port}"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_irrelevant_query_key(key)
    ]
    query_pairs.sort(key=lambda item: (item[0].casefold(), item[0], item[1]))
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, _normalize_path(parts.path), query, ""))


def is_pdf_url(url: str) -> bool:
    """Return whether the URL path identifies a PDF, ignoring query/fragment."""

    try:
        return urlsplit(url).path.casefold().endswith(".pdf")
    except (TypeError, ValueError):
        return False


def _ascii_text(value: object) -> str:
    if value is None:
        return ""
    return (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def safe_identifier(
    value: object,
    *,
    max_length: int = 80,
    fallback: str = "item",
) -> str:
    """Create a lowercase path-safe identifier containing no traversal tokens."""

    if max_length < 1:
        raise ValueError("max_length must be positive")
    identifier = re.sub(r"[^A-Za-z0-9]+", "-", _ascii_text(value)).strip("-._")
    identifier = re.sub(r"-{2,}", "-", identifier).casefold()
    if not identifier or identifier in {".", ".."}:
        identifier = re.sub(
            r"[^A-Za-z0-9]+", "-", _ascii_text(fallback)
        ).strip("-._").casefold()
    identifier = identifier or "item"
    identifier = identifier[:max_length].rstrip("-._") or "item"[:max_length]
    if identifier.upper() in _WINDOWS_RESERVED_NAMES:
        identifier = f"_{identifier}"
        identifier = identifier[:max_length]
    return identifier


def safe_filename(
    value: object,
    *,
    max_length: int = 160,
    fallback: str = "document",
    extension: str | None = None,
) -> str:
    """Create a single portable filename while preserving a safe extension.

    Directory separators, leading dots, control characters, and platform-reserved
    names cannot survive this transformation, so callers may safely join the result
    beneath an already-selected output directory.
    """

    if max_length < 1:
        raise ValueError("max_length must be positive")

    raw = _ascii_text(value).replace("/", "-").replace("\\", "-").strip()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", raw)
    raw = re.sub(r"[-_]{2,}", "-", raw).strip(" .-_")

    if extension is None:
        stem, separator, raw_extension = raw.rpartition(".")
        if not separator or not stem:
            stem, raw_extension = raw, ""
    else:
        stem = raw.rsplit(".", 1)[0] if "." in raw else raw
        raw_extension = str(extension).lstrip(".")

    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_")
    if not stem:
        stem = safe_identifier(fallback, max_length=max_length)
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"

    clean_extension = re.sub(r"[^A-Za-z0-9]+", "", raw_extension).casefold()
    suffix = f".{clean_extension}" if clean_extension else ""
    available = max_length - len(suffix)
    if available < 1:
        # A caller-supplied tiny limit must still produce a safe, bounded filename.
        return (stem + suffix)[:max_length].rstrip(" .")
    stem = stem[:available].rstrip("-_") or "f"[:available]
    return stem + suffix


def make_document_id(
    source_id: str,
    url: str,
    *,
    digest_length: int = 16,
) -> str:
    """Build a stable document ID from source identity and canonical source URL."""

    if not isinstance(digest_length, int) or not 8 <= digest_length <= 64:
        raise ValueError("digest_length must be between 8 and 64")
    prefix = safe_identifier(source_id, max_length=64, fallback="source")
    canonical_url = canonicalize_url(url)
    digest = sha256_text(f"{source_id.strip()}\0{canonical_url}")[:digest_length]
    return f"{prefix}-{digest}"


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp suitable for provenance records."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Readable aliases for callers that prefer domain terminology.
content_hash_bytes = sha256_bytes
content_hash_text = sha256_text
stable_document_id = make_document_id
