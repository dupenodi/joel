"""§10.3 — reciprocal rank fusion across lanes. Verbatim port of the plan's
own reference implementation; the only change is operating on `RetrievedDoc`
(`.id`/`.ts`) instead of an unnamed `d`.

Why k=60: rank-1 in one list scores 0.0164; rank-4 in THREE lists scores
0.0469 — consensus across lanes beats a single strong vote from one lane.
Age decay applies only inside tie windows (`EPS`), never as a blanket boost.
"""

from __future__ import annotations

from collections import defaultdict

from joel.retrieve.lanes import RetrievedDoc

RRF_K = 60
PER_SOURCE_CAP = 3
EPS = 0.005


def rrf_fuse(lists: dict[str, list[RetrievedDoc]], top_n: int = 20) -> list[RetrievedDoc]:
    score: dict[str, float] = defaultdict(float)
    best: dict[str, RetrievedDoc] = {}
    for _name, docs in lists.items():
        contributed: dict[str, int] = defaultdict(int)
        for rank, d in enumerate(docs, 1):
            if contributed[d.id] >= PER_SOURCE_CAP:
                continue
            contributed[d.id] += 1
            score[d.id] += 1.0 / (RRF_K + rank)
            best.setdefault(d.id, d)

    ranked = sorted(score, key=score.get, reverse=True)
    out: list[str] = []
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and score[ranked[i]] - score[ranked[j + 1]] < EPS:
            j += 1
        out += sorted(ranked[i : j + 1], key=lambda doc_id: best[doc_id].ts or "", reverse=True)
        i = j + 1
    return [best[doc_id] for doc_id in out[:top_n]]


__all__ = ["rrf_fuse", "RRF_K", "PER_SOURCE_CAP", "EPS"]
