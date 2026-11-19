"""Framework-free definitions for the verified foundation components."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Node:
    key: str
    kind: Literal["service", "storage"]
    display_name: str
    runtime: Literal["python", "postgresql"]


@dataclass(frozen=True)
class Edge:
    key: str
    source_key: str
    target_key: str
    relation: Literal["persists_to"]


API = Node("service:api", "service", "Platform API", "python")
DATABASE = Node("storage:postgres", "storage", "PostgreSQL", "postgresql")
API_DATABASE = Edge("link:api:persists_to:postgres", API.key, DATABASE.key, "persists_to")


def safe_metadata(metadata: dict[str, str]) -> dict[str, str]:
    """Reject unknown keys AND values; never silently log rejected content."""
    if set(metadata) != {"runtime"} or metadata["runtime"] not in {"python", "postgresql"}:
        raise ValueError("Metadata is outside the foundation allowlist")
    return dict(metadata)
