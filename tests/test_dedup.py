from __future__ import annotations

from agent import db
from agent.dedup import hash_file, is_duplicate


def test_hash_file_is_deterministic(tmp_path):
    file_path = tmp_path / "doc.pdf"
    file_path.write_bytes(b"same content")

    assert hash_file(file_path) == hash_file(file_path)


def test_hash_file_differs_for_different_content(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"content A")
    b.write_bytes(b"content B")

    assert hash_file(a) != hash_file(b)


def test_is_duplicate_false_when_not_logged(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    file_path = tmp_path / "doc.pdf"
    file_path.write_bytes(b"never seen before")

    assert is_duplicate(file_path, db_path=db_path) is False


def test_is_duplicate_true_after_logging(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    file_path = tmp_path / "doc.pdf"
    file_path.write_bytes(b"already filed")
    file_hash = hash_file(file_path)

    connection = db.get_connection(db_path)
    try:
        connection.execute(
            """
            INSERT INTO processed_files (file_hash, original_filename, new_filepath, status)
            VALUES (?, ?, ?, ?)
            """,
            (file_hash, "doc.pdf", "ClientFiles/Smith/doc.pdf", "filed"),
        )
        connection.commit()
    finally:
        connection.close()

    assert is_duplicate(file_path, db_path=db_path) is True
