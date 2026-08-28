"""LLM classification: Claude proposes structured fields, never freehand text.

client_manifest.json and doctype_rules.json are the ground truth - the model
is told to pick from those lists (or return null) rather than invent a
client name or document type on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import anthropic

from agent.schemas import DocumentClassification

MODEL = "claude-sonnet-5"

# A classifier only needs the front matter of a document to identify it -
# capping input keeps latency/cost bounded and limits how much of a
# client's document leaves the machine per call.
MAX_TEXT_CHARS = 6000

CLASSIFY_TOOL = {
    "name": "record_classification",
    "description": "Record the structured classification of a scanned document.",
    "input_schema": DocumentClassification.model_json_schema(),
}


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify_document(
    text: str,
    client_manifest: dict,
    doctype_rules: dict,
    client: anthropic.Anthropic | None = None,
) -> DocumentClassification:
    client = client or anthropic.Anthropic()

    client_names = [c["name"] for c in client_manifest["clients"]]
    doc_types = list(doctype_rules["doc_types"].keys())

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        tools=[CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "record_classification"},
        messages=[{"role": "user", "content": _build_prompt(text, client_names, doc_types)}],
    )

    tool_use = next(block for block in response.content if block.type == "tool_use")
    return DocumentClassification.model_validate(tool_use.input)


def _build_prompt(text: str, client_names: list[str], doc_types: list[str]) -> str:
    return f"""You are classifying a scanned document for a law firm's filing system.

Known clients (choose an exact match from this list, or null if none fit):
{json.dumps(client_names)}

Known document types (choose an exact match from this list):
{json.dumps(doc_types)}

Extracted document text:
---
{text[:MAX_TEXT_CHARS]}
---

Call record_classification with your best determination. If the text is too
garbled or ambiguous to confidently match a client, set client_name_match to
null and confidence_score low rather than guessing - a human reviews anything
under threshold."""
