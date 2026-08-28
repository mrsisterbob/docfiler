"""Deterministic filename construction from a classification.

No LLM calls, no I/O - given the same inputs these always return the same
output, which is what makes it safe to trust with real client files instead
of whatever string Claude happened to produce.
"""

from __future__ import annotations

import re

_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_-]+")


class NamingError(ValueError):
    """Raised when a classification doesn't have enough to build a safe filename."""


def sanitize_component(value: str) -> str:
    """Collapse a free-text field into a filesystem-safe token."""
    return _UNSAFE_CHARS_RE.sub("_", value.strip()).strip("_")


def build_filename(
    client_name_match: str,
    doc_type: str,
    doc_date: str,
    doctype_rules: dict,
    extension: str = "pdf",
) -> str:
    if not client_name_match:
        raise NamingError("client_name_match is required to build a filename")

    rule = doctype_rules["doc_types"].get(doc_type)
    if rule is None:
        raise NamingError(f"Unknown doc_type: {doc_type!r}")

    client_token = sanitize_component(client_name_match)
    doc_type_token = sanitize_component(rule["short_code"])

    return f"{doc_date}_{client_token}_{doc_type_token}.{extension}"
