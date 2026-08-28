"""Entry point: watches _Intake_Drop and runs the full filing pipeline.

dedup -> extractor -> classifier -> namer/router -> file move -> db log,
with anything low-confidence or unextractable falling back to _NeedsReview/.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agent import db
from agent.classifier import classify_document, load_json
from agent.dedup import hash_file, is_duplicate
from agent.extractor import extract_text
from agent.fileops import has_file_changed, safe_move, unique_destination
from agent.namer import NamingError, build_filename
from agent.router import RoutingError, resolve_destination_path
from agent.watcher import watch_intake

# When frozen by PyInstaller, bundled data (--add-data) is unpacked to a temp
# dir at sys._MEIPASS, not next to the exe - fall back to that when present.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

# Runtime dirs (intake/review/output) must live beside the actual exe/script,
# not inside the temp extraction dir, so they use the exe's location when frozen.
RUNTIME_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

INTAKE_DIR = RUNTIME_DIR / "_Intake_Drop"
NEEDS_REVIEW_DIR = RUNTIME_DIR / "_NeedsReview"
CLIENT_FILES_DIR = RUNTIME_DIR / "ClientFiles"
CONFIG_DIR = BASE_DIR / "config"

CONFIDENCE_THRESHOLD = 0.85

CLIENT_MANIFEST = load_json(CONFIG_DIR / "client_manifest.json")
DOCTYPE_RULES = load_json(CONFIG_DIR / "doctype_rules.json")

LOG_PATH = RUNTIME_DIR / "docfiler.log"
_log_handler = logging.handlers.RotatingFileHandler(
    str(LOG_PATH), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])

def _log(connection, file_hash: str, original_filename: str, new_filepath: str, status: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO processed_files (file_hash, original_filename, new_filepath, timestamp, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_hash, original_filename, new_filepath, datetime.now(timezone.utc).isoformat(), status),
    )
    connection.commit()


def _send_to_needs_review(file_path: Path, connection, file_hash: str, status: str) -> None:
    """Move file_path into _NeedsReview and log why. Encodes the failure
    reason into the filename itself so a human triaging the folder doesn't
    have to cross-reference the DB to know what went wrong.
    """
    try:
        NEEDS_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        tagged_name = f"{file_path.stem}__{status}{file_path.suffix}"
        destination = unique_destination(NEEDS_REVIEW_DIR / tagged_name)
        safe_move(file_path, destination)
        _log(connection, file_hash, file_path.name, str(destination), status)
    except OSError:
        logging.exception("failed to route %s to _NeedsReview (status=%s)", file_path, status)
        _quarantine_in_place(file_path, connection, file_hash, status)


def _quarantine_in_place(file_path: Path, connection, file_hash: str, status: str) -> None:
    """Last-resort fallback when even the move into _NeedsReview fails.

    Without this, a file that fails triage sits in _Intake_Drop unchanged -
    it generates no new watchdog event, so the watcher never revisits it and
    it is silently lost. Renaming it (even in place) is itself a filesystem
    event, and the .quarantined marker stops it from ever being picked up
    by process_file again as if it were a fresh, untriaged drop.
    """
    quarantined_status = f"{status}_quarantined"
    try:
        marker_path = file_path.with_name(f"{file_path.stem}__QUARANTINED{file_path.suffix}")
        marker_path = unique_destination(marker_path)
        file_path.rename(marker_path)
        logging.critical(
            "file stranded in intake, quarantined in place: %s -> %s (status=%s)",
            file_path, marker_path, quarantined_status,
        )
        _log(connection, file_hash, file_path.name, str(marker_path), quarantined_status)
    except OSError:
        logging.critical(
            "file stranded in intake and could not even be renamed: %s (status=%s) - manual intervention required",
            file_path, quarantined_status, exc_info=True,
        )
        _log(connection, file_hash, file_path.name, str(file_path), quarantined_status)


def process_file(file_path_str: str) -> None:
    file_path = Path(file_path_str)
    if not file_path.exists():
        return

    try:
        initial_stat = file_path.stat()
        file_hash = hash_file(file_path)
    except OSError:
        logging.exception("could not hash %s (locked or unreadable); leaving in place for retry", file_path)
        return

    connection = db.get_connection(db.DB_PATH)
    try:
        if is_duplicate(file_path, db_path=db.DB_PATH):
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                logging.exception("could not remove duplicate %s", file_path)
            return

        try:
            extraction = extract_text(file_path)
        except Exception:
            logging.exception("extraction failed for %s", file_path)
            _send_to_needs_review(file_path, connection, file_hash, "extraction_failed")
            return

        try:
            classification = classify_document(extraction.text, CLIENT_MANIFEST, DOCTYPE_RULES)
        except Exception:
            logging.exception("classification failed for %s", file_path)
            _send_to_needs_review(file_path, connection, file_hash, "classification_failed")
            return

        if classification.confidence_score < CONFIDENCE_THRESHOLD or not classification.client_name_match:
            _send_to_needs_review(file_path, connection, file_hash, "low_confidence")
            return

        try:
            filename = build_filename(
                classification.client_name_match,
                classification.doc_type,
                classification.doc_date,
                DOCTYPE_RULES,
                extension=file_path.suffix.lstrip(".") or "pdf",
            )
            destination = resolve_destination_path(
                classification.client_name_match,
                filename,
                CLIENT_MANIFEST,
                CLIENT_FILES_DIR,
            )
        except (NamingError, RoutingError):
            logging.exception("naming/routing failed for %s", file_path)
            _send_to_needs_review(file_path, connection, file_hash, "naming_or_routing_failed")
            return

        try:
            changed = has_file_changed(file_path, initial_stat)
        except OSError:
            logging.exception("file vanished before final move: %s", file_path)
            return

        if changed:
            # File changed after we hashed/extracted/classified it - a late
            # write landed inside the debounce's blind spot. What we
            # classified is stale, so don't file it under that verdict.
            # Bail out without deleting/moving anything; the write that
            # changed it will itself fire a fresh watchdog event that
            # re-runs this function against the new, now-stable content.
            logging.warning(
                "file changed after classification, deferring to next stability check: %s", file_path
            )
            return

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = unique_destination(destination)
            safe_move(file_path, destination)
            _log(connection, file_hash, file_path.name, str(destination), "filed")
        except OSError:
            logging.exception("file move failed for %s -> %s", file_path, destination)
            _send_to_needs_review(file_path, connection, file_hash, "move_failed")
    finally:
        connection.close()


def _acquire_single_instance_lock() -> object:
    """Prevent two copies of the frozen exe racing over the same intake dir."""
    lock_path = RUNTIME_DIR / "docfiler.lock"
    lock_file = open(lock_path, "w")
    try:
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        logging.error("another docfiler instance is already running (lock: %s)", lock_path)
        raise SystemExit(1)
    return lock_file


def main() -> None:
    lock_file = _acquire_single_instance_lock()
    try:
        db.init_db()
        INTAKE_DIR.mkdir(parents=True, exist_ok=True)
        NEEDS_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        CLIENT_FILES_DIR.mkdir(parents=True, exist_ok=True)

        watcher = watch_intake(str(INTAKE_DIR), process_file)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            watcher.stop()
    finally:
        lock_file.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
