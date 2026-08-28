"""Filesystem move helpers shared by main.py's pipeline.

Pulled out of main.py so they have no import-time side effects (no log
handlers, no config loads) and can be unit tested directly.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

MOVE_RETRIES = 5
MOVE_RETRY_DELAY_SECONDS = 1.0


def safe_move(
    src: Path,
    dest: Path,
    retries: int = MOVE_RETRIES,
    retry_delay_seconds: float = MOVE_RETRY_DELAY_SECONDS,
) -> None:
    """Move src to dest, retrying on OSError (Windows AV/scanner locks)."""
    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            shutil.move(str(src), str(dest))
            return
        except OSError as exc:
            last_error = exc
            logging.warning("move attempt %d/%d failed for %s: %s", attempt + 1, retries, src, exc)
            time.sleep(retry_delay_seconds)
    raise last_error


def unique_destination(destination: Path) -> Path:
    """Avoid silently overwriting an existing file with the same deterministic name."""
    if not destination.exists():
        return destination

    stem, suffix, parent = destination.stem, destination.suffix, destination.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}__{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def has_file_changed(path: Path, previous_stat) -> bool:
    """True if path's size or mtime differ from a previously captured os.stat_result.

    Used to detect a late write landing inside the watcher's debounce blind
    spot, between when a file was classified and when it's about to be moved.
    """
    current_stat = path.stat()
    return current_stat.st_size != previous_stat.st_size or current_stat.st_mtime != previous_stat.st_mtime
