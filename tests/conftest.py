from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"


@pytest.fixture
def client_manifest() -> dict:
    from agent.classifier import load_json

    return load_json(CONFIG_DIR / "client_manifest.json")


@pytest.fixture
def doctype_rules() -> dict:
    from agent.classifier import load_json

    return load_json(CONFIG_DIR / "doctype_rules.json")
