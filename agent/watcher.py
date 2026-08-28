"""Intake directory watcher for _Intake_Drop.

Watches the intake directory for new/modified files using watchdog, and
invokes a processing callback once each file's size and mtime have been
stable for a debounce interval (avoids processing files still being copied).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

DEBOUNCE_SECONDS = 3.0
POLL_INTERVAL_SECONDS = 0.5

ProcessCallback = Callable[[str], None]


class _PendingFile:
    __slots__ = ("path", "size", "mtime", "last_change")

    def __init__(self, path: str, size: int, mtime: float):
        self.path = path
        self.size = size
        self.mtime = mtime
        self.last_change = time.monotonic()


class IntakeEventHandler(FileSystemEventHandler):
    def __init__(self, pending: dict, lock: threading.Lock):
        super().__init__()
        self._pending = pending
        self._lock = lock

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._track(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._track(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._track(event.dest_path)

    def _track(self, path: str) -> None:
        try:
            stat = os.stat(path)
        except OSError:
            return

        with self._lock:
            self._pending[path] = _PendingFile(path, stat.st_size, stat.st_mtime)


class IntakeWatcher:
    """Watches an intake directory and calls back once files are stable."""

    def __init__(
        self,
        intake_dir: str,
        on_stable: ProcessCallback,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ):
        self.intake_dir = intake_dir
        self.on_stable = on_stable
        self.debounce_seconds = debounce_seconds
        self.poll_interval = poll_interval

        self._pending: dict[str, _PendingFile] = {}
        self._lock = threading.Lock()
        self._observer = Observer()
        self._stop_event = threading.Event()
        self._checker_thread: threading.Thread | None = None

    def start(self) -> None:
        os.makedirs(self.intake_dir, exist_ok=True)

        handler = IntakeEventHandler(self._pending, self._lock)
        self._observer.schedule(handler, self.intake_dir, recursive=False)
        self._observer.start()

        self._stop_event.clear()
        self._checker_thread = threading.Thread(target=self._check_loop, daemon=True)
        self._checker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._observer.stop()
        self._observer.join()
        if self._checker_thread is not None:
            self._checker_thread.join()

    def _check_loop(self) -> None:
        while not self._stop_event.is_set():
            self._check_pending()
            self._stop_event.wait(self.poll_interval)

    def _check_pending(self) -> None:
        now = time.monotonic()
        stable_paths = []

        with self._lock:
            for path, pending in list(self._pending.items()):
                try:
                    stat = os.stat(path)
                except OSError:
                    del self._pending[path]
                    continue

                if stat.st_size != pending.size or stat.st_mtime != pending.mtime:
                    pending.size = stat.st_size
                    pending.mtime = stat.st_mtime
                    pending.last_change = now
                    continue

                if now - pending.last_change >= self.debounce_seconds:
                    stable_paths.append(path)
                    del self._pending[path]

        for path in stable_paths:
            try:
                self.on_stable(path)
            except Exception:
                logging.exception("on_stable callback failed for %s", path)


def watch_intake(
    intake_dir: str,
    on_stable: ProcessCallback,
    debounce_seconds: float = DEBOUNCE_SECONDS,
) -> IntakeWatcher:
    watcher = IntakeWatcher(intake_dir, on_stable, debounce_seconds=debounce_seconds)
    watcher.start()
    return watcher
