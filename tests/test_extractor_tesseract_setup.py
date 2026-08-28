from __future__ import annotations

import pytest

from agent.extractor import TesseractNotConfiguredError, _ensure_tesseract_available


def test_ensure_tesseract_available_raises_clear_error_when_missing(monkeypatch):
    import pytesseract

    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "definitely-not-a-real-binary")

    with pytest.raises(TesseractNotConfiguredError, match="not found on PATH"):
        _ensure_tesseract_available()


def test_ensure_tesseract_available_passes_when_on_path(monkeypatch):
    monkeypatch.setattr("agent.extractor.shutil.which", lambda _cmd: r"C:\fake\tesseract.exe")

    _ensure_tesseract_available()  # should not raise
