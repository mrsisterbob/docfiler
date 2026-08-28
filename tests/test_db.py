from __future__ import annotations

from agent import db


def test_get_connection_creates_schema(tmp_path):
    db_path = tmp_path / "test.db"
    connection = db.get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_files'"
        ).fetchone()
        assert row is not None
    finally:
        connection.close()


def test_get_connection_enables_wal(tmp_path):
    db_path = tmp_path / "test.db"
    connection = db.get_connection(db_path)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        connection.close()


def test_get_connection_sets_busy_timeout(tmp_path):
    db_path = tmp_path / "test.db"
    connection = db.get_connection(db_path)
    try:
        timeout_ms = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout_ms == 5000
    finally:
        connection.close()


def test_indexes_exist(tmp_path):
    db_path = tmp_path / "test.db"
    connection = db.get_connection(db_path)
    try:
        index_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_processed_files_timestamp" in index_names
        assert "idx_processed_files_status" in index_names
        assert "idx_processed_files_status_timestamp" in index_names
    finally:
        connection.close()


def test_file_hash_unique_constraint_enforced(tmp_path):
    import sqlite3

    db_path = tmp_path / "test.db"
    connection = db.get_connection(db_path)
    try:
        connection.execute(
            """
            INSERT INTO processed_files (file_hash, original_filename, new_filepath, status)
            VALUES (?, ?, ?, ?)
            """,
            ("abc123", "a.pdf", "ClientFiles/a.pdf", "filed"),
        )
        connection.commit()

        try:
            connection.execute(
                """
                INSERT INTO processed_files (file_hash, original_filename, new_filepath, status)
                VALUES (?, ?, ?, ?)
                """,
                ("abc123", "b.pdf", "ClientFiles/b.pdf", "filed"),
            )
            connection.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True

        assert raised
    finally:
        connection.close()
