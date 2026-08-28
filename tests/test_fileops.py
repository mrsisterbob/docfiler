from __future__ import annotations

from pathlib import Path

import pytest

from agent.fileops import has_file_changed, safe_move, unique_destination


def test_unique_destination_no_collision(tmp_path):
    dest = tmp_path / "file.pdf"
    assert unique_destination(dest) == dest


def test_unique_destination_single_collision(tmp_path):
    dest = tmp_path / "file.pdf"
    dest.write_bytes(b"existing")

    result = unique_destination(dest)

    assert result == tmp_path / "file__2.pdf"


def test_unique_destination_multiple_collisions(tmp_path):
    (tmp_path / "file.pdf").write_bytes(b"a")
    (tmp_path / "file__2.pdf").write_bytes(b"b")
    (tmp_path / "file__3.pdf").write_bytes(b"c")

    result = unique_destination(tmp_path / "file.pdf")

    assert result == tmp_path / "file__4.pdf"


def test_safe_move_happy_path(tmp_path):
    src = tmp_path / "src.pdf"
    dest = tmp_path / "dest.pdf"
    src.write_bytes(b"content")

    safe_move(src, dest)

    assert not src.exists()
    assert dest.read_bytes() == b"content"


def test_safe_move_retries_then_raises(tmp_path, monkeypatch):
    src = tmp_path / "src.pdf"
    dest = tmp_path / "dest.pdf"
    src.write_bytes(b"content")

    call_count = 0

    def always_fail(_src, _dest):
        nonlocal call_count
        call_count += 1
        raise OSError("simulated lock")

    monkeypatch.setattr("agent.fileops.shutil.move", always_fail)
    monkeypatch.setattr("agent.fileops.time.sleep", lambda _seconds: None)

    with pytest.raises(OSError):
        safe_move(src, dest, retries=3, retry_delay_seconds=0)

    assert call_count == 3


def test_safe_move_succeeds_after_transient_failure(tmp_path, monkeypatch):
    import os

    src = tmp_path / "src.pdf"
    dest = tmp_path / "dest.pdf"
    src.write_bytes(b"content")

    call_count = 0

    def fail_once_then_succeed(s, d):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("simulated transient lock")
        os.rename(s, d)

    monkeypatch.setattr("agent.fileops.shutil.move", fail_once_then_succeed)
    monkeypatch.setattr("agent.fileops.time.sleep", lambda _seconds: None)

    safe_move(src, dest, retries=3, retry_delay_seconds=0)

    assert dest.read_bytes() == b"content"
    assert call_count == 2


def test_has_file_changed_false_when_stable(tmp_path):
    path = tmp_path / "file.pdf"
    path.write_bytes(b"content")
    previous_stat = path.stat()

    assert has_file_changed(path, previous_stat) is False


def test_has_file_changed_true_after_write(tmp_path):
    path = tmp_path / "file.pdf"
    path.write_bytes(b"content")
    previous_stat = path.stat()

    path.write_bytes(b"content plus more data appended later")

    assert has_file_changed(path, previous_stat) is True
