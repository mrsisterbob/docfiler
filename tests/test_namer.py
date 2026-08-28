from __future__ import annotations

import pytest

from agent.namer import NamingError, build_filename


def test_build_filename_happy_path(doctype_rules):
    filename = build_filename("Smith", "WarrantyDeed", "2026-08-20", doctype_rules)
    assert filename == "2026-08-20_Smith_WarrantyDeed.pdf"


def test_build_filename_sanitizes_unsafe_chars(doctype_rules):
    filename = build_filename("O'Brien & Sons", "Correspondence", "2026-01-01", doctype_rules)
    assert filename == "2026-01-01_O_Brien_Sons_Correspondence.pdf"


def test_build_filename_missing_client_raises(doctype_rules):
    with pytest.raises(NamingError):
        build_filename("", "WarrantyDeed", "2026-08-20", doctype_rules)


def test_build_filename_unknown_doc_type_raises(doctype_rules):
    with pytest.raises(NamingError):
        build_filename("Smith", "NotARealDocType", "2026-08-20", doctype_rules)


def test_build_filename_custom_extension(doctype_rules):
    filename = build_filename("Smith", "WarrantyDeed", "2026-08-20", doctype_rules, extension="tif")
    assert filename.endswith(".tif")
