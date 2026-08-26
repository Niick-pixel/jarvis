"""Who is waiting on you, and which job runs already have a driver.

A job run parked at the gate is an `asyncio.Event` here and a row in `tool_calls` on disk. The
event is the fast path: decide in the UI and the run continues within milliseconds. The row is the
durable one: if the process restarts while a run is parked, the event is gone but the run is not,
and approving it starts a fresh driver that picks up exactly where the rows say it stopped.
"""

from __future__ import annotations

import asyncio


class Approvals:
    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._driving: set[str] = set()

    def waiter(self, job_run_id: str) -> asyncio.Event:
        return self._events.setdefault(job_run_id, asyncio.Event())

    def notify(self, job_run_id: str) -> None:
        """A decision landed. Wakes the driver if there is one; harmless if there is not."""
        event = self._events.get(job_run_id)
        if event is not None:
            event.set()

    def clear(self, job_run_id: str) -> None:
        self._events.pop(job_run_id, None)

    def claim(self, job_run_id: str) -> bool:
        """One driver per run. Returns False if this run is already being driven."""
        if job_run_id in self._driving:
            return False
        self._driving.add(job_run_id)
        return True

    def release(self, job_run_id: str) -> None:
        self._driving.discard(job_run_id)
        self.clear(job_run_id)

    def is_driving(self, job_run_id: str) -> bool:
        return job_run_id in self._driving
