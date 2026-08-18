"""Background ingest scheduler — per-connector interval, not a human click."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence


def ingest_is_schedulable(
    provider: str, channel_ids: Sequence[str] | None = None
) -> bool:
    """Slack stays connected but must not sync until channels are picked."""
    if provider == "slack" and not channel_ids:
        return False
    return True


def start_scheduler(
    tick: Callable[[], None],
    *,
    interval_sec: float = 30,
) -> threading.Event:
    """Run `tick` every interval_sec until the returned event is set."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval_sec):
            try:
                tick()
            except Exception:
                continue

    thread = threading.Thread(target=loop, name="joel-ingest-scheduler", daemon=True)
    thread.start()
    return stop


__all__ = ["ingest_is_schedulable", "start_scheduler"]
