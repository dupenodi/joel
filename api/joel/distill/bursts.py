"""Burst grouping (§7.1) — the first step of distillation, and independent
of the LLM. Adjacent same-author messages within `GAP_MINUTES` collapse into
one burst before a thread is ever sent to `distill_thread` (§9.2), so a
five-message "same person thinking out loud" run costs one row, not five.
"""

from __future__ import annotations

from datetime import datetime, timezone

from joel.models import Burst, CanonicalDoc

GAP_MINUTES = 7

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def group_bursts(msgs: list[CanonicalDoc]) -> list[Burst]:
    """Group one thread's messages into bursts by author + time gap.

    A new burst starts when the author changes, or more than `GAP_MINUTES`
    elapses since the last message in the current burst. Messages without a
    timestamp sort first and never bridge a gap (treated as epoch).
    """
    ordered = sorted(msgs, key=lambda m: m.timestamp or _EPOCH)
    bursts: list[Burst] = []
    current: Burst | None = None

    for m in ordered:
        ts = m.timestamp or _EPOCH
        author = m.author_raw or "unknown"
        is_new = (
            current is None
            or author != current.author_raw
            or (ts - current.end_ts).total_seconds() > GAP_MINUTES * 60
        )
        if is_new:
            if current is not None:
                bursts.append(current)
            current = Burst(
                burst_id=f"{m.thread_id}_b{len(bursts)}",
                thread_id=m.thread_id or "",
                author_raw=author,
                text=m.body,
                message_external_ids=[m.external_id],
                start_ts=ts,
                end_ts=ts,
                has_reactions=bool(m.extra.get("reactions")),
            )
        else:
            assert current is not None
            current.text += "\n" + m.body
            current.message_external_ids.append(m.external_id)
            current.end_ts = ts
            current.has_reactions = current.has_reactions or bool(m.extra.get("reactions"))

    if current is not None:
        bursts.append(current)
    return bursts


__all__ = ["group_bursts", "GAP_MINUTES"]
