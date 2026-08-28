from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.schemas import DocumentClassification


def test_valid_classification():
    doc = DocumentClassification(
        client_name_match="Smith",
        doc_type="WarrantyDeed",
        doc_date="2026-08-20",
        confidence_score=0.94,
    )
    assert doc.confidence_score == 0.94


def test_null_client_name_match_allowed():
    doc = DocumentClassification(
        client_name_match=None,
        doc_type="Correspondence",
        doc_date="2026-08-20",
        confidence_score=0.2,
    )
    assert doc.client_name_match is None


@pytest.mark.parametrize("bad_date", ["08-20-2026", "2026/08/20", "not-a-date", ""])
def test_invalid_doc_date_rejected(bad_date):
    with pytest.raises(ValidationError):
        DocumentClassification(
            client_name_match="Smith",
            doc_type="WarrantyDeed",
            doc_date=bad_date,
            confidence_score=0.9,
        )


@pytest.mark.parametrize("bad_score", [-0.1, 1.1, 2.0])
def test_confidence_score_out_of_range_rejected(bad_score):
    with pytest.raises(ValidationError):
        DocumentClassification(
            client_name_match="Smith",
            doc_type="WarrantyDeed",
            doc_date="2026-08-20",
            confidence_score=bad_score,
        )
