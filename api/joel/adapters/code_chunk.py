"""Language-aware code chunks. Never split a function body."""

from __future__ import annotations

import re

_CLASS = re.compile(
    r"^(class|struct|interface|impl|enum|type)\s+\w+",
    re.M,
)
_FN = re.compile(
    r"^\s{0,4}(def |fn |func |function |async def |[A-Za-z_:<>~]+\s+\w+\s*\()",
    re.M,
)
MAX_LINES = 120


def _line_count(text: str) -> int:
    return text.count("\n") + (1 if text else 0)


def _split_at(src: str, pattern: re.Pattern[str]) -> list[str] | None:
    matches = list(pattern.finditer(src))
    if not matches:
        return None
    parts: list[str] = []
    prefix = src[: matches[0].start()]
    if prefix.strip():
        parts.append(prefix)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(src)
        parts.append(src[match.start() : end])
    return parts


def first_symbol(chunk: str, path: str) -> str:
    for pattern in (_CLASS, _FN):
        match = pattern.search(chunk)
        if match:
            line = chunk[match.start() :].splitlines()[0].strip()
            return line[:80]
    name = path.rsplit("/", 1)[-1]
    return name


def chunk_code(path: str, src: str) -> list[str]:
    """Split a file at class then function boundaries. Oversized functions stay whole."""
    del path
    if not src.strip():
        return []
    units = _split_at(src, _CLASS) or [src]
    out: list[str] = []
    for unit in units:
        if _line_count(unit) <= MAX_LINES:
            out.append(unit)
            continue
        fns = _split_at(unit, _FN)
        if not fns:
            out.append(unit)
            continue
        out.extend(fns)
    return [part for part in out if part.strip()]


__all__ = ["MAX_LINES", "chunk_code", "first_symbol"]
