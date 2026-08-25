"""Watching indexed folders for changes.

Windows drives mounted under /mnt/ do not deliver inotify events to WSL2, so those paths are
polled instead. The observer in use is recorded per source and shown in the UI, because "why
didn't my edit get picked up" should have a visible answer rather than being a mystery.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from server.models.knowledge import Observer

log = logging.getLogger(__name__)
DEBOUNCE_S = 2.0
WINDOWS_MOUNTS = ("/mnt/",)


def observer_for(path: Path) -> Observer:
    """Native inotify, unless the path lives on a Windows drive."""
    return "polling" if str(path).startswith(WINDOWS_MOUNTS) else "native"


class Watcher:
    """Debounced change notification: one observer per source, stopped when it is removed."""

    def __init__(self, on_change: Callable[[str], None]) -> None:
        self._on_change = on_change
        self._observers: dict[str, object] = {}
        self._pending: dict[str, asyncio.TimerHandle] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, source_id: str, path: Path, kind: Observer) -> bool:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer as NativeObserver
            from watchdog.observers.polling import PollingObserver
        except ImportError:
            return False

        self._loop = asyncio.get_running_loop()
        self.stop(source_id)

        outer = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event: object) -> None:
                if getattr(event, "is_directory", False):
                    return
                outer._schedule(source_id)

        observer = PollingObserver(timeout=5) if kind == "polling" else NativeObserver()
        try:
            observer.schedule(Handler(), str(path), recursive=True)
            observer.daemon = True
            observer.start()
        except Exception as exc:  # noqa: BLE001 - a watch failing must not break indexing
            log.warning("watch of %s failed: %s", path, exc)
            return False
        self._observers[source_id] = observer
        return True

    def _schedule(self, source_id: str) -> None:
        """Called from the watchdog thread; hop back to the loop and debounce."""
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._debounce, source_id)

    def _debounce(self, source_id: str) -> None:
        if handle := self._pending.pop(source_id, None):
            handle.cancel()
        loop = self._loop
        if loop is None:
            return
        # An editor save can fire several events; reindex once things settle.
        self._pending[source_id] = loop.call_later(DEBOUNCE_S, lambda: self._fire(source_id))

    def _fire(self, source_id: str) -> None:
        self._pending.pop(source_id, None)
        try:
            self._on_change(source_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("reindex trigger for %s failed: %s", source_id, exc)

    def stop(self, source_id: str) -> None:
        observer = self._observers.pop(source_id, None)
        if observer is None:
            return
        try:
            observer.stop()  # type: ignore[attr-defined]
            observer.join(timeout=2)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            log.warning("stopping watch %s failed: %s", source_id, exc)

    def stop_all(self) -> None:
        for source_id in list(self._observers):
            self.stop(source_id)
