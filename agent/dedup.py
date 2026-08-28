"""Duplicate-file detection: has this exact file already been filed?

Hashes the file's contents rather than trusting its name or path, so a
user saving the same document twice - even under a different filename -
is recognized as a repeat instead of being filed again.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from agent import db

_HASH_CHUNK_SIZE = 65536


def hash_file(file_path: str | Path) -> str:
    """Compute the SHA-256 hash of a file's contents."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_duplicate(file_path: str | Path, db_path: str | Path = db.DB_PATH) -> bool:
    """Return True if a file with this content hash is already in processed_files."""
    file_hash = hash_file(file_path)
    connection = db.get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT 1 FROM processed_files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None
    finally:
        connection.close()
