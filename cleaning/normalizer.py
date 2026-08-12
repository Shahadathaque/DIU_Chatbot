"""Conservative Unicode, whitespace, line, and table normalization."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple


_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_BROKEN_WORD = re.compile(r"(?<=\w)-\n\s*(?=[a-z])")


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "").replace("\u200b", "")
    text = _BROKEN_WORD.sub("", text)
    lines: List[str] = []
    previous: Optional[str] = None
    for raw_line in text.split("\n"):
        line = _HORIZONTAL_SPACE.sub(" ", raw_line).strip()
        line = re.sub(r"^[▪◦‣]\s*", "• ", line)
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            previous = None
            continue
        if line == previous:
            continue
        lines.append(line)
        previous = line
    normalized = "\n".join(lines).strip()
    return _EXCESS_BLANK_LINES.sub("\n\n", normalized)


def normalize_cell(value: object) -> str:
    return " ".join(normalize_text(value).split())


def normalize_matrix(rows: Iterable[Sequence[object]]) -> List[List[str]]:
    matrix = [[normalize_cell(cell) for cell in row] for row in rows]
    matrix = [row for row in matrix if any(row)]
    if not matrix:
        return []
    width = max(len(row) for row in matrix)
    matrix = [row + [""] * (width - len(row)) for row in matrix]
    keep_columns = [
        index for index in range(width) if any(row[index] for row in matrix)
    ]
    return [[row[index] for index in keep_columns] for row in matrix]


def split_header_and_rows(
    rows: Iterable[Sequence[object]],
) -> Tuple[List[str], List[List[str]]]:
    matrix = normalize_matrix(rows)
    if len(matrix) < 2:
        return [], []
    return matrix[0], matrix[1:]


def text_removed_percent(source_length: int, cleaned_length: int) -> float:
    if source_length <= 0:
        return 0.0
    removed = max(0, source_length - cleaned_length)
    return round((removed / source_length) * 100.0, 2)
