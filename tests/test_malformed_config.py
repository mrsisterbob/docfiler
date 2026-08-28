from __future__ import annotations

import json

import pytest

from agent.classifier import load_json
from agent.namer import NamingError, build_filename
from agent.router import RoutingError, resolve_destination_path


def test_load_json_malformed_raises(tmp_path):
    bad_json = tmp_path / "broken.json"
    bad_json.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_json(bad_json)


def test_build_filename_with_empty_doctype_rules_raises():
    with pytest.raises(NamingError):
        build_filename("Smith", "WarrantyDeed", "2026-08-20", {"doc_types": {}})


def test_resolve_destination_with_empty_client_manifest_raises():
    with pytest.raises(RoutingError):
        resolve_destination_path("Smith", "file.pdf", {"clients": []}, "ClientFiles")
