from __future__ import annotations

import shutil

import fitz
import pytest

from agent.extractor import extract_text

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


def _make_pdf(path, text: str | None) -> None:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_extract_digital_text(tmp_path):
    pdf_path = tmp_path / "digital.pdf"
    _make_pdf(pdf_path, "This is a born-digital page with plenty of real text content on it.")

    result = extract_text(pdf_path)

    assert result.method == "digital"
    assert "born-digital" in result.text
    assert result.confidence == 100.0


@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract binary not installed/on PATH")
def test_extract_blank_page_falls_back_to_ocr(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    _make_pdf(pdf_path, None)  # no text layer at all, e.g. a scanned raster page

    result = extract_text(pdf_path)

    assert result.method == "ocr"
    assert result.page_count == 1


def test_extract_zero_byte_file_raises(tmp_path):
    empty_path = tmp_path / "empty.pdf"
    empty_path.write_bytes(b"")

    with pytest.raises(Exception):
        extract_text(empty_path)
