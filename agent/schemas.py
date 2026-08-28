"""Structured output contract for the classifier LLM call.

The model only ever returns these typed fields - namer.py and router.py
trust them directly and never parse free-text from the LLM.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DocumentClassification(BaseModel):
    client_name_match: str | None = Field(
        description="Best-matching client name from client_manifest.json, or null if no confident match"
    )
    doc_type: str = Field(
        description="Matching doc type key from doctype_rules.json"
    )
    doc_date: str = Field(
        description="Document date in YYYY-MM-DD format"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence in client_name_match and doc_type together, 0.0-1.0"
    )

    @field_validator("doc_date")
    @classmethod
    def _validate_doc_date(cls, value: str) -> str:
        if not _DATE_RE.match(value):
            raise ValueError(f"doc_date must be YYYY-MM-DD, got {value!r}")
        return value
