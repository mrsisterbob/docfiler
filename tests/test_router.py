from __future__ import annotations

from pathlib import Path

import pytest

from agent.router import RoutingError, resolve_destination_path


def test_resolve_destination_by_exact_name(client_manifest):
    dest = resolve_destination_path("Smith", "file.pdf", client_manifest, "ClientFiles")
    assert dest == Path("ClientFiles/Clients/Smith/file.pdf")


def test_resolve_destination_by_alias(client_manifest):
    dest = resolve_destination_path("John Smith", "file.pdf", client_manifest, "ClientFiles")
    assert dest == Path("ClientFiles/Clients/Smith/file.pdf")


def test_resolve_destination_unknown_client_raises(client_manifest):
    with pytest.raises(RoutingError):
        resolve_destination_path("Nobody", "file.pdf", client_manifest, "ClientFiles")
