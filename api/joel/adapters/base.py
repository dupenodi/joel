"""Shared adapter core — raw provider dict → CanonicalDoc (§6).

Connectors fetch. Manifests declare field mapping. This module is the only
place that turns a payload into a CanonicalDoc. Provider-specific *code*
belongs in `pre` hooks (quote-strip, markup clean, code chunk), not in a
seventh archetype.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from joel.models import CanonicalDoc, build_doc_id, compute_content_hash
from joel.visibility import apply as apply_visibility

Archetype = Literal[
    "conversation",
    "tracker",
    "document",
    "record",
    "code",
    "transcript",
]
TriageResult = Literal["new", "changed", "unchanged"]
TimestampKind = Literal["epoch", "epoch_ms", "iso"]
PreHook = Callable[[dict[str, Any]], dict[str, Any]]
UrlBuilder = Callable[[Mapping[str, Any]], str | None]


@dataclass(frozen=True)
class SourceManifest:
    """Declarative mapping from a provider payload onto one archetype."""

    provider: str
    archetype: Archetype
    external_id: str
    body: str
    author: str | None = None
    title: str | None = None
    container: str | None = None
    timestamp: tuple[str, TimestampKind] | None = None
    # (primary, fallback) — e.g. Slack ("thread_ts", "ts")
    thread: tuple[str, str] | None = None
    # parent = get(a) when get(a) != get(b); else None (Slack roots)
    parent_if_differs: tuple[str, str] | None = None
    parent: str | None = None
    url: str | UrlBuilder | None = None
    extra: tuple[str, ...] = ()
    participants: str | None = None
    pre: tuple[PreHook, ...] = ()
    # Prefixed onto external_id before build_doc_id (github issue_ vs pr_)
    id_prefix: str = ""
    # Prefixed onto resolved thread_id so issue/PR threads don't share an artifact id
    thread_prefix: str = ""
    granularity: str = "document"
    min_body_chars: int = 20
    default_title: str = "(untitled)"


def _get(raw: Mapping[str, Any], key: str | None) -> Any:
    if key is None:
        return None
    cur: Any = raw
    for part in key.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _parse_timestamp(value: Any, kind: TimestampKind) -> datetime | None:
    if value is None or value == "":
        return None
    if kind == "epoch":
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if kind == "epoch_ms":
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    if kind == "iso":
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        ts = datetime.fromisoformat(text)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    raise ValueError(f"unknown timestamp kind {kind!r}")


def _resolve_url(manifest: SourceManifest, raw: Mapping[str, Any]) -> str | None:
    if manifest.url is None:
        return None
    if callable(manifest.url):
        return manifest.url(raw)
    return _as_str(_get(raw, manifest.url))


def _participants(raw: Mapping[str, Any], key: str | None) -> list[str]:
    value = _get(raw, key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out: list[str] = []
        for item in value:
            s = _as_str(item)
            if s:
                out.append(s)
        return out
    s = _as_str(value)
    return [s] if s else []


def adapt(manifest: SourceManifest, raw: Mapping[str, Any]) -> CanonicalDoc | None:
    """Map one raw payload to a CanonicalDoc, or None if the body is too short."""
    payload: dict[str, Any] = dict(raw)
    for hook in manifest.pre:
        payload = hook(payload)

    body = (_as_str(_get(payload, manifest.body)) or "").strip()
    if len(body) < manifest.min_body_chars:
        return None

    external = _as_str(_get(payload, manifest.external_id))
    if not external:
        raise ValueError(
            f"{manifest.provider}: missing external_id field {manifest.external_id!r}"
        )
    external_id = f"{manifest.id_prefix}{external}"

    title_val = _as_str(_get(payload, manifest.title)) if manifest.title else None
    title = (title_val or body[:80].split("\n", 1)[0] or manifest.default_title).strip()

    thread_id: str | None = None
    if manifest.thread is not None:
        primary, fallback = manifest.thread
        thread_id = _as_str(_get(payload, primary)) or _as_str(_get(payload, fallback))
        if thread_id and manifest.thread_prefix:
            thread_id = f"{manifest.thread_prefix}{thread_id}"

    parent_id: str | None = None
    if manifest.parent_if_differs is not None:
        a_key, b_key = manifest.parent_if_differs
        a = _as_str(_get(payload, a_key))
        b = _as_str(_get(payload, b_key))
        if a and b and a != b:
            parent_id = a
    elif manifest.parent is not None:
        parent_id = _as_str(_get(payload, manifest.parent))

    ts: datetime | None = None
    if manifest.timestamp is not None:
        field_name, kind = manifest.timestamp
        ts = _parse_timestamp(_get(payload, field_name), kind)

    extra: dict[str, Any] = {}
    for key in manifest.extra:
        val = _get(payload, key)
        if val is not None:
            extra[key] = val

    return apply_visibility(
        CanonicalDoc(
            doc_id=build_doc_id(manifest.provider, external_id),
            source_type=manifest.provider,
            external_id=external_id,
            title=title,
            body=body,
            extra=extra,
            author_raw=_as_str(_get(payload, manifest.author)) if manifest.author else None,
            participants_raw=_participants(payload, manifest.participants),
            container=_as_str(_get(payload, manifest.container)) if manifest.container else None,
            url=_resolve_url(manifest, payload),
            timestamp=ts,
            thread_id=thread_id,
            parent_id=parent_id,
            content_hash=compute_content_hash(title, body),
            granularity=manifest.granularity,
        )
    )


def adapt_many(
    manifest: SourceManifest, raws: Iterable[Mapping[str, Any]]
) -> list[CanonicalDoc]:
    docs: list[CanonicalDoc] = []
    for raw in raws:
        doc = adapt(manifest, raw)
        if doc is not None:
            docs.append(doc)
    return docs


def triage(doc: CanonicalDoc, known: Mapping[str, str]) -> TriageResult:
    """Classify a doc against the once-per-job hash map (§6.1)."""
    prior = known.get(doc.doc_id)
    if prior is None:
        return "new"
    if prior != doc.content_hash:
        return "changed"
    return "unchanged"


@dataclass
class TriageReport:
    new: list[CanonicalDoc] = field(default_factory=list)
    changed: list[CanonicalDoc] = field(default_factory=list)
    unchanged: list[CanonicalDoc] = field(default_factory=list)
    dirty_thread_ids: set[str] = field(default_factory=set)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
        }


def triage_batch(
    docs: Iterable[CanonicalDoc], known: Mapping[str, str]
) -> TriageReport:
    report = TriageReport()
    for doc in docs:
        result = triage(doc, known)
        if result == "new":
            report.new.append(doc)
            if doc.thread_id:
                report.dirty_thread_ids.add(doc.thread_id)
        elif result == "changed":
            report.changed.append(doc)
            if doc.thread_id:
                report.dirty_thread_ids.add(doc.thread_id)
        else:
            report.unchanged.append(doc)
    return report


def group_threads(
    docs: Iterable[CanonicalDoc], *, min_size: int = 3
) -> dict[str, list[CanonicalDoc]]:
    """Bucket docs by thread_id. Only threads with ≥ min_size items are returned."""
    buckets: dict[str, list[CanonicalDoc]] = defaultdict(list)
    for doc in docs:
        if doc.thread_id:
            buckets[doc.thread_id].append(doc)
    out: dict[str, list[CanonicalDoc]] = {}
    for thread_id, items in buckets.items():
        if len(items) >= min_size:
            out[thread_id] = sorted(
                items,
                key=lambda d: (d.timestamp is None, d.timestamp or datetime.min.replace(tzinfo=timezone.utc)),
            )
    return out


__all__ = [
    "SourceManifest",
    "TriageReport",
    "adapt",
    "adapt_many",
    "triage",
    "triage_batch",
    "group_threads",
]
