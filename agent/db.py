"""Local persistence for the docfiler pipeline: one row per file processed.

file_hash is the de-dup key - callers check this table before reprocessing
a file they've already filed, and status records whether an attempt fully
succeeded or needs a human to look at it.
"""

from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

# docfiler.db must persist next to the running app, not inside PyInstaller's
# temp extraction dir (sys._MEIPASS), so it survives across frozen runs.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent.resolve()
else:
    APP_DIR = Path(__file__).parent.parent.resolve()

DB_PATH = APP_DIR / "docfiler.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    new_filepath TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processed_files_timestamp ON processed_files(timestamp);
CREATE INDEX IF NOT EXISTS idx_processed_files_status ON processed_files(status);
CREATE INDEX IF NOT EXISTS idx_processed_files_status_timestamp ON processed_files(status, timestamp);
"""


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Open a connection to docfiler.db, creating processed_files if needed."""
    connection = sqlite3.connect(db_path, timeout=30)
    # WAL tolerates concurrent readers/writers far better than the default
    # rollback journal, which matters when AV scans docfiler.db on write.
    # busy_timeout is SQLite's own lock-wait (separate from the Python driver's
    # connect-level timeout above) - both are needed, not redundant.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def init_db(db_path: str | Path = DB_PATH) -> None:
    get_connection(db_path).close()


if __name__ == "__main__":
    init_db()
    print(f"[db] initialized {DB_PATH}")
