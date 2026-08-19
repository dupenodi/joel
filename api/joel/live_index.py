"""In-memory vector index with a hot-reload `apply()` (§8.3) — the seam that
keeps a scheduler ingesting every 15 minutes from going invisible until a
restart, "the single worst bug available in this design" per the plan.

Brute-force dot product over a normalized float32 matrix, with numpy boolean
masks over parallel metadata arrays for the §10.2 retrieval-lane filters.
Readers take one immutable `_Snapshot` by reference; `apply()` builds a new
snapshot and swaps it in with a single attribute assignment, which is atomic
under the GIL, so a `search()` in flight always sees one consistent
(matrix, meta) pair even while a write is landing concurrently. Do not
reach for hnswlib before `len(ids) > 250_000` (§8.3) — same interface then.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

META_FIELDS = (
    "granularity",
    "artifact_class",
    "validity",
    "resolved",
    "period",
    "source_type",
    "visibility",
)
META_FALLBACK = {"visibility": "org"}

COMPACT_TOMBSTONE_RATIO = 0.2


@dataclass(frozen=True)
class _Snapshot:
    matrix: np.ndarray  # (N, dim) float32, unit-norm rows
    ids: list[str]
    meta: dict[str, np.ndarray]  # field -> (N,) object array
    forgotten: np.ndarray  # (N,) bool
    row_of: dict[str, int]


def _empty_snapshot(dim: int) -> _Snapshot:
    return _Snapshot(
        matrix=np.zeros((0, dim), dtype=np.float32),
        ids=[],
        meta={f: np.zeros(0, dtype=object) for f in META_FIELDS},
        forgotten=np.zeros(0, dtype=bool),
        row_of={},
    )


def _normalize(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


class LiveIndex:
    def __init__(self, npz_path: str | Path, dim: int = 384):
        self.npz_path = Path(npz_path)
        self.dim = dim
        self._write_lock = threading.Lock()
        self._snapshot = self._load()

    def _load(self) -> _Snapshot:
        if not self.npz_path.exists():
            return _empty_snapshot(self.dim)
        data = np.load(self.npz_path, allow_pickle=True)
        matrix = data["matrix"].astype(np.float32)
        ids = list(data["ids"])
        n = len(ids)
        files = set(data.files)
        meta = {}
        for f in META_FIELDS:
            if f in files:
                meta[f] = data[f]
            else:
                fill = META_FALLBACK.get(f, "")
                meta[f] = np.array([fill] * n, dtype=object)
        forgotten = data["forgotten"].astype(bool)
        row_of = {doc_id: i for i, doc_id in enumerate(ids)}
        return _Snapshot(matrix=matrix, ids=ids, meta=meta, forgotten=forgotten, row_of=row_of)

    def _save(self, snap: _Snapshot) -> None:
        self.npz_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "matrix": snap.matrix,
            "ids": np.array(snap.ids, dtype=object),
            "forgotten": snap.forgotten,
            **snap.meta,
        }
        # np.savez appends ".npz" itself unless the name already ends with
        # it, so the temp file must keep that suffix or the rename below
        # silently misses (savez would write "<tmp>.npz" instead).
        tmp = self.npz_path.with_name(self.npz_path.stem + ".tmp.npz")
        np.savez(tmp, **payload)
        tmp.replace(self.npz_path)

    @property
    def version_count(self) -> int:
        """Row count of the current snapshot, incl. tombstoned rows."""
        return len(self._snapshot.ids)

    def apply(
        self,
        upserts: dict[str, tuple[np.ndarray, dict[str, object]]],
        deleted: Iterable[str] = (),
    ) -> None:
        """Hot-apply upserts/deletes and persist. `upserts`: id -> (vector,
        meta-dict); vectors are normalized here regardless of caller state.
        Known ids overwrite in place; unknown ids append. Deletes set the
        tombstone bit and never resize the matrix (§8.3) — call `compact()`
        separately once tombstones pile up.
        """
        with self._write_lock:
            snap = self._snapshot
            matrix = snap.matrix.copy()
            ids = list(snap.ids)
            meta = {f: snap.meta[f].copy() for f in META_FIELDS}
            forgotten = snap.forgotten.copy()
            row_of = dict(snap.row_of)

            new_vecs: list[np.ndarray] = []
            new_meta: dict[str, list[object]] = {f: [] for f in META_FIELDS}
            new_ids: list[str] = []

            for doc_id, (vec, m) in upserts.items():
                vec = _normalize(vec)
                if doc_id in row_of:
                    r = row_of[doc_id]
                    matrix[r] = vec
                    for f in META_FIELDS:
                        meta[f][r] = m.get(f)
                    forgotten[r] = False
                else:
                    new_vecs.append(vec)
                    new_ids.append(doc_id)
                    for f in META_FIELDS:
                        new_meta[f].append(m.get(f))

            if new_vecs:
                stacked = np.stack(new_vecs).astype(np.float32)
                matrix = np.vstack([matrix, stacked]) if matrix.shape[0] else stacked
                base = len(ids)
                for i, doc_id in enumerate(new_ids):
                    row_of[doc_id] = base + i
                ids.extend(new_ids)
                forgotten = np.concatenate([forgotten, np.zeros(len(new_ids), dtype=bool)])
                for f in META_FIELDS:
                    meta[f] = np.concatenate([meta[f], np.array(new_meta[f], dtype=object)])

            for doc_id in deleted:
                if doc_id in row_of:
                    forgotten[row_of[doc_id]] = True

            new_snap = _Snapshot(matrix=matrix, ids=ids, meta=meta, forgotten=forgotten, row_of=row_of)
            self._save(new_snap)
            self._snapshot = new_snap  # single atomic swap — see module docstring

    def mask(self, **filters: object) -> np.ndarray:
        """Boolean mask over the CURRENT snapshot's rows (caller must use it
        against that same snapshot — take `index.snapshot()` first if you
        need the mask and the matrix to agree under a concurrent apply)."""
        snap = self._snapshot
        m = np.ones(len(snap.ids), dtype=bool)
        for field, value in filters.items():
            col = snap.meta[field]
            if isinstance(value, (set, frozenset, list, tuple)):
                allowed = list(value)
                if not allowed:
                    return np.zeros(len(snap.ids), dtype=bool)
                hit = np.zeros(len(snap.ids), dtype=bool)
                for item in allowed:
                    hit |= col == item
                m &= hit
            else:
                m &= col == value
        return m

    def snapshot(self) -> _Snapshot:
        return self._snapshot

    def search(
        self, query_vec: np.ndarray, mask: np.ndarray | None = None, k: int = 20
    ) -> list[tuple[str, float]]:
        """Dot-product top-k over a consistent snapshot, excluding forgotten
        rows and (optionally) further restricted by `mask`."""
        snap = self._snapshot  # one read = one consistent (matrix, meta) pair
        n = snap.matrix.shape[0]
        if n == 0:
            return []
        active = ~snap.forgotten
        if mask is not None:
            active = active & mask
        if not active.any():
            return []
        q = _normalize(query_vec)
        scores = snap.matrix @ q
        scores = np.where(active, scores, -np.inf)
        k = min(k, n)
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(snap.ids[i], float(scores[i])) for i in top if np.isfinite(scores[i])]

    def compact(self) -> None:
        """Drop tombstoned rows and rewrite the npz. Call when tombstones
        exceed COMPACT_TOMBSTONE_RATIO of rows, or on demand (§8.3)."""
        with self._write_lock:
            snap = self._snapshot
            keep = ~snap.forgotten
            matrix = snap.matrix[keep]
            ids = [doc_id for doc_id, k in zip(snap.ids, keep) if k]
            meta = {f: snap.meta[f][keep] for f in META_FIELDS}
            forgotten = np.zeros(len(ids), dtype=bool)
            row_of = {doc_id: i for i, doc_id in enumerate(ids)}
            new_snap = _Snapshot(matrix=matrix, ids=ids, meta=meta, forgotten=forgotten, row_of=row_of)
            self._save(new_snap)
            self._snapshot = new_snap

    def needs_compact(self) -> bool:
        snap = self._snapshot
        if len(snap.ids) == 0:
            return False
        return snap.forgotten.sum() / len(snap.ids) > COMPACT_TOMBSTONE_RATIO


__all__ = ["LiveIndex", "META_FIELDS", "META_FALLBACK", "COMPACT_TOMBSTONE_RATIO"]
