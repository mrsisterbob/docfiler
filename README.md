# docfiler

<!-- AUTO-STATS:START -->
![Lines of source](https://img.shields.io/badge/source-831_lines-c9a24b)
![Tests](https://img.shields.io/badge/tests-47-4a8a5c)
<!-- AUTO-STATS:END -->

Automated document intake and filing: watches a drop folder, extracts text (digital-first, OCR
fallback), classifies each document against a client/doc-type manifest via Claude, and files it
under a deterministic, standardized name. Anything low-confidence or unmatched is set aside for
human review instead of being silently misfiled.

## Architecture

```
main.py               Entry point: watches _Intake_Drop, runs the full pipeline
                       (dedup -> extractor -> classifier -> namer/router -> move -> log),
                       with quarantine fallbacks so a failing file is never silently lost.
agent/watcher.py       Debounced folder watcher (watchdog) - waits for a file's size/mtime
                       to stabilize before processing, so mid-copy files are never grabbed.
agent/extractor.py     Text extraction: PyMuPDF digital text first, Tesseract OCR fallback
                       for scanned pages, with per-page confidence scoring.
agent/classifier.py    Claude tool-call classification - client name and doc type are matched
                       only against config/client_manifest.json and doctype_rules.json; the
                       model returns null/low-confidence rather than inventing a match.
agent/namer.py         Deterministic filename construction (no LLM, no I/O) - same inputs
                       always produce the same filename.
agent/router.py        Deterministic destination-path resolution from the client manifest.
agent/dedup.py         SHA-256 content-hash duplicate detection (not filename-based).
config/                client_manifest.json (clients + folders + aliases) and
                       doctype_rules.json (document types + filename short codes).
sample_docs/           Two synthetic fixture PDFs (a warranty deed, a trust amendment) to
                       drop into _Intake_Drop and watch the pipeline run. Not real documents.
tests/                 pytest suite covering db, dedup, extractor (incl. a Tesseract-setup
                       check), fileops, namer, router, schemas, malformed config, and a full
                       pipeline integration test.
```

## Setup

```
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for running tests
```

Requires a local Tesseract OCR install for scanned documents (e.g. `choco install tesseract` on
Windows, or see https://github.com/UB-Mannheim/tesseract/wiki).

Set `ANTHROPIC_API_KEY` in your environment (the classifier calls Claude). Edit
`config/client_manifest.json` and `config/doctype_rules.json` for your own clients/document
types before running - the sample data (Smith/Doe/Harmon/Whitfield) is placeholder.

Run `python main.py`, then copy a PDF from `sample_docs/` into `_Intake_Drop/` to watch the full
dedup -> extract -> classify -> name -> file pipeline. `docfiler.db`, the runtime folders
(`_Intake_Drop/`, `_NeedsReview/`, `ClientFiles/`), and any real documents are gitignored - this
repo is the pipeline, not the filing cabinet.

## Tests

```
python -m pytest tests/ -v
```
