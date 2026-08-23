"""In-flight runs: cancellation and fan-out to every attached client.

Not in the PLAN.md tree, which put cancellation in `cancel.py`. It grew one responsibility because
generation runs as a background task rather than inside the HTTP handler: closing the browser must
not kill a generation, and reopening it must reattach. Both need the same registry, so they live
together rather than sharing state across two modules.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from server.models.stream import StopReason, StreamEvent

QUEUE_MAX = 2048


@dataclass
class LiveRun:
    run_id: str
    message_id: str
    conversation_id: str
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    stop_reason: StopReason = "user_stop"
    finished: bool = False
    last_index: int = -1
    done: asyncio.Event = field(default_factory=asyncio.Event)
    """Set once the run's rows are written, so a nudge can continue from a settled partial."""
    subscribers: set[asyncio.Queue[StreamEvent | None]] = field(default_factory=set)

    def publish(self, event: StreamEvent) -> None:
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stalled client must never stall generation; it will resume from the DB.
                self.subscribers.discard(queue)

    def close(self) -> None:
        self.finished = True
        self.done.set()
        for queue in list(self.subscribers):
            with _ignore_full():
                queue.put_nowait(None)
        self.subscribers.clear()


class LiveRuns:
    def __init__(self) -> None:
        self._runs: dict[str, LiveRun] = {}

    def start(self, run_id: str, message_id: str, conversation_id: str) -> LiveRun:
        run = LiveRun(run_id=run_id, message_id=message_id, conversation_id=conversation_id)
        self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> LiveRun | None:
        return self._runs.get(run_id)

    def stop(self, run_id: str, reason: StopReason = "user_stop") -> bool:
        run = self._runs.get(run_id)
        if run is None or run.finished:
            return False
        run.stop_reason = reason
        run.cancelled.set()
        return True

    def subscribe(self, run_id: str) -> tuple[LiveRun, asyncio.Queue[StreamEvent | None]] | None:
        run = self._runs.get(run_id)
        if run is None or run.finished:
            return None
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(maxsize=QUEUE_MAX)
        run.subscribers.add(queue)
        return run, queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[StreamEvent | None]) -> None:
        if run := self._runs.get(run_id):
            run.subscribers.discard(queue)

    def finish(self, run_id: str) -> None:
        if run := self._runs.get(run_id):
            run.close()

    def forget(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def active_ids(self) -> list[str]:
        return [r.run_id for r in self._runs.values() if not r.finished]


class _ignore_full:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, *_: object) -> bool:
        return exc_type is asyncio.QueueFull
