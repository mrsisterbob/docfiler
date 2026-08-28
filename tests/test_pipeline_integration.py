"""End-to-end integration test for main.process_file.

main.py has import-time side effects (opens a rotating log handler at the
real project's RUNTIME_DIR, loads real config), so instead of redirecting
those globals per-test, this test drives it through its public entry point
and monkeypatches only the directories/thresholds process_file actually
reads at call time, keeping every read/write confined to tmp_path.
"""

from __future__ import annotations

from unittest.mock import patch

import fitz
import pytest

import main
from agent import db
from agent.schemas import DocumentClassification


@pytest.fixture(autouse=True)
def _isolate_runtime_dirs(tmp_path, monkeypatch):
    needs_review = tmp_path / "_NeedsReview"
    client_files = tmp_path / "ClientFiles"
    db_path = tmp_path / "docfiler.db"

    monkeypatch.setattr(main, "NEEDS_REVIEW_DIR", needs_review)
    monkeypatch.setattr(main, "CLIENT_FILES_DIR", client_files)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(db_path)

    return {"needs_review": needs_review, "client_files": client_files, "db_path": db_path}


def _make_digital_pdf(path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_high_confidence_file_gets_filed(tmp_path, _isolate_runtime_dirs):
    src = tmp_path / "incoming.pdf"
    _make_digital_pdf(src, "A born-digital warranty deed with plenty of real page text on it.")

    stub_classification = DocumentClassification(
        client_name_match="Smith",
        doc_type="WarrantyDeed",
        doc_date="2026-08-20",
        confidence_score=0.95,
    )

    with patch("main.classify_document", return_value=stub_classification):
        main.process_file(str(src))

    assert not src.exists()
    filed = list(_isolate_runtime_dirs["client_files"].rglob("*.pdf"))
    assert len(filed) == 1
    assert filed[0].name == "2026-08-20_Smith_WarrantyDeed.pdf"

    connection = db.get_connection(_isolate_runtime_dirs["db_path"])
    try:
        row = connection.execute("SELECT status FROM processed_files").fetchone()
    finally:
        connection.close()
    assert row[0] == "filed"


def test_low_confidence_file_routes_to_needs_review(tmp_path, _isolate_runtime_dirs):
    src = tmp_path / "incoming.pdf"
    _make_digital_pdf(src, "A born-digital document with plenty of real page text on it.")

    stub_classification = DocumentClassification(
        client_name_match="Smith",
        doc_type="WarrantyDeed",
        doc_date="2026-08-20",
        confidence_score=0.40,
    )

    with patch("main.classify_document", return_value=stub_classification):
        main.process_file(str(src))

    assert not src.exists()
    review_files = list(_isolate_runtime_dirs["needs_review"].glob("*low_confidence*"))
    assert len(review_files) == 1

    connection = db.get_connection(_isolate_runtime_dirs["db_path"])
    try:
        row = connection.execute("SELECT status FROM processed_files").fetchone()
    finally:
        connection.close()
    assert row[0] == "low_confidence"


def test_classification_failure_routes_to_needs_review(tmp_path, _isolate_runtime_dirs):
    src = tmp_path / "incoming.pdf"
    _make_digital_pdf(src, "A born-digital document with plenty of real page text on it.")

    with patch("main.classify_document", side_effect=RuntimeError("API down")):
        main.process_file(str(src))

    assert not src.exists()
    review_files = list(_isolate_runtime_dirs["needs_review"].glob("*classification_failed*"))
    assert len(review_files) == 1


def test_zero_byte_file_routes_to_needs_review(tmp_path, _isolate_runtime_dirs):
    src = tmp_path / "empty.pdf"
    src.write_bytes(b"")

    # hash_file succeeds on an empty file (it's a valid, if trivial, hash);
    # it's PyMuPDF's extract_text that rejects it as EmptyFileError, which
    # main.py's try/except around extract_text catches and triages normally.
    main.process_file(str(src))

    assert not src.exists()
    review_files = list(_isolate_runtime_dirs["needs_review"].glob("*extraction_failed*"))
    assert len(review_files) == 1


def test_duplicate_file_is_deleted_without_reprocessing(tmp_path, _isolate_runtime_dirs):
    src = tmp_path / "incoming.pdf"
    _make_digital_pdf(src, "A born-digital document with plenty of real page text on it.")

    stub_classification = DocumentClassification(
        client_name_match="Smith",
        doc_type="WarrantyDeed",
        doc_date="2026-08-20",
        confidence_score=0.95,
    )

    with patch("main.classify_document", return_value=stub_classification):
        main.process_file(str(src))

    # Drop an identical-content file under a different name.
    duplicate = tmp_path / "duplicate_copy.pdf"
    duplicate.write_bytes(
        (list(_isolate_runtime_dirs["client_files"].rglob("*.pdf"))[0]).read_bytes()
    )

    with patch("main.classify_document", return_value=stub_classification) as mock_classify:
        main.process_file(str(duplicate))
        mock_classify.assert_not_called()

    assert not duplicate.exists()
