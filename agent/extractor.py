"""Local text extraction: born-digital PDF text first, OCR fallback for scans.

Scanned deeds/estate documents usually have no embedded text layer at all -
PyMuPDF's get_text() silently returns an empty string on them rather than
raising, so "too short to trust" is the actual signal we fall back on, not
an exception.
"""

from __future__ import annotations

import io
import shutil
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz
import pytesseract
from PIL import Image


class TesseractNotConfiguredError(RuntimeError):
    """Raised when OCR fallback is needed but the tesseract binary isn't reachable.

    Distinguishes a machine-wide setup problem (not installed / not on PATH)
    from a per-document OCR failure, so the two don't look identical in logs.
    """


def _ensure_tesseract_available() -> None:
    cmd = pytesseract.pytesseract.tesseract_cmd
    if shutil.which(cmd) is None and not Path(cmd).is_file():
        raise TesseractNotConfiguredError(
            f"tesseract binary {cmd!r} not found on PATH. Install it "
            "(e.g. `choco install tesseract` on Windows, or "
            "https://github.com/UB-Mannheim/tesseract/wiki) or set "
            "pytesseract.pytesseract.tesseract_cmd to its full path."
        )

# Below this many characters, a page's digital text layer is treated as
# missing/unreliable (e.g. a scanned raster page with no OCR layer at all,
# or just a stray watermark) rather than genuine content.
MIN_DIGITAL_CHARS_PER_PAGE = 40

# Cap how many pages get OCR'd on a fallback - a classifier only needs the
# first page or two of a deed/agreement to identify it, and OCR is slow.
MAX_OCR_PAGES = 5

# Render scanned pages at this DPI before handing them to Tesseract - lower
# is faster but hurts OCR accuracy on small print (legal descriptions, etc).
OCR_RENDER_DPI = 300


@dataclass
class ExtractionResult:
    text: str
    confidence: float  # 0-100
    method: str  # "digital" or "ocr"
    page_count: int


def extract_text(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path)

    with fitz.open(path) as doc:
        page_count = doc.page_count
        digital_pages = [doc.load_page(i).get_text().strip() for i in range(page_count)]

        if _is_digital_text_reliable(digital_pages):
            return ExtractionResult(
                text="\n\n".join(p for p in digital_pages if p),
                confidence=100.0,
                method="digital",
                page_count=page_count,
            )

        return _ocr_fallback(doc, page_count)


def _is_digital_text_reliable(pages: list[str]) -> bool:
    if not pages:
        return False
    return all(len(p) >= MIN_DIGITAL_CHARS_PER_PAGE for p in pages)


def _ocr_fallback(doc: fitz.Document, page_count: int) -> ExtractionResult:
    _ensure_tesseract_available()

    pages_to_ocr = min(page_count, MAX_OCR_PAGES)
    texts: list[str] = []
    confidences: list[float] = []

    for i in range(pages_to_ocr):
        pixmap = doc.load_page(i).get_pixmap(dpi=OCR_RENDER_DPI)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        text, confidence = _ocr_image(image)
        texts.append(text)
        confidences.append(confidence)

    # Weakest-page confidence, not an average - one unreadable page
    # shouldn't get diluted by clean ones when a human still needs to
    # decide whether to trust the result.
    overall_confidence = min(confidences) if confidences else 0.0

    return ExtractionResult(
        text="\n\n".join(t for t in texts if t),
        confidence=overall_confidence,
        method="ocr",
        page_count=page_count,
    )


def _ocr_image(image: Image.Image) -> tuple[str, float]:
    if image.mode != "L":
        image = image.convert("L")

    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = [w for w in data["text"] if w.strip()]
    word_confidences = [
        int(c) for c, w in zip(data["conf"], data["text"]) if w.strip() and int(c) >= 0
    ]

    text = " ".join(words)
    confidence = (sum(word_confidences) / len(word_confidences)) if word_confidences else 0.0
    return text, confidence
