"""Typed deterministic analysis and artifact contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
ANALYSIS_ERRORS = frozenset(
    {
        "invalid_numeric",
        "unknown_column",
        "too_many_groups",
        "numeric_overflow",
        "source_unavailable",
        "source_changed",
        "analysis_timeout",
        "analysis_failed",
        "artifact_too_large",
    }
)


@dataclass(frozen=True)
class Ratio:
    name: str
    numerator: str
    denominator: str
    scale: float = 1.0


@dataclass(frozen=True)
class AnalysisSpec:
    numeric_columns: tuple[str, ...]
    chart_column: str
    group_by: str | None = None
    ratios: tuple[Ratio, ...] = ()

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "AnalysisSpec":
        return cls(
            tuple(data["numeric_columns"]),
            data["chart_column"],
            data.get("group_by"),
            tuple(Ratio(**r) for r in data.get("ratios", [])),
        )


@dataclass(frozen=True)
class Bundle:
    report: bytes
    chart: bytes


@dataclass(frozen=True)
class Artifact:
    id: UUID
    run_id: UUID
    attempt_id: UUID
    kind: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class AnalysisFailure(Exception):
    def __init__(self, code: str):
        self.code = code if code in ANALYSIS_ERRORS else "analysis_failed"
        super().__init__(self.code)


class SourceReader(Protocol):
    def read(self, file_id: UUID) -> tuple[bytes, str, str]: ...
