"""Deterministic destination resolution: client name -> folder -> full path.

client_manifest.json is the single source of truth for where a client's
files live - this only ever looks a name up against that list, it never
constructs or guesses a path.
"""

from __future__ import annotations

from pathlib import Path


class RoutingError(ValueError):
    """Raised when a classified client has no folder mapping in the manifest."""


def _find_client_entry(client_name_match: str, client_manifest: dict) -> dict:
    for client in client_manifest["clients"]:
        if client_name_match == client["name"] or client_name_match in client.get("aliases", []):
            return client
    raise RoutingError(f"No manifest entry (or alias) matches client: {client_name_match!r}")


def resolve_destination_path(
    client_name_match: str,
    filename: str,
    client_manifest: dict,
    base_dir: str | Path,
) -> Path:
    entry = _find_client_entry(client_name_match, client_manifest)
    return Path(base_dir) / entry["folder"] / filename
