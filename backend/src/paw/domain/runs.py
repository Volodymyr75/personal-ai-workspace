"""Durable execution contracts, independent of adapters."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

LEASE_SECONDS = 15
HEARTBEAT_SECONDS = 3
MAX_ATTEMPTS = 3
MAX_ATTEMPT_SECONDS = 45
Status = Literal["queued", "running", "completed", "failed"]


class IdempotencyConflict(Exception):
    pass


@dataclass(frozen=True)
class Run:
    id: UUID
    project_id: UUID
    request_id: UUID
    correlation_id: UUID | None
    task_type: str
    delay_seconds: int
    outcome: str
    status: Status
    attempt_id: UUID | None
    attempt_count: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    lease_expires_at: datetime | None
    attempt_deadline: datetime | None
    error_code: str | None
    output: dict[str, str] | None


@dataclass(frozen=True)
class RunEvent:
    id: UUID
    sequence: int
    run_id: UUID
    attempt_id: UUID | None
    event_type: str
    recorded_at: datetime


class RunRepository(Protocol):
    def create(
        self,
        project_id: UUID,
        request_id: UUID,
        correlation_id: UUID | None,
        delay_seconds: int,
        outcome: str,
    ) -> Run: ...
    def get(self, run_id: UUID) -> Run: ...
    def events(self, run_id: UUID, after: int, limit: int) -> list[RunEvent]: ...
    def claim(self) -> Run | None: ...
    def heartbeat(self, run_id: UUID, attempt_id: UUID) -> bool: ...
    def finish(self, run_id: UUID, attempt_id: UUID, error_code: str | None) -> bool: ...
