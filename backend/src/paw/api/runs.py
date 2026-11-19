from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from paw.domain.runs import RunRepository, Status

router = APIRouter(prefix="/api/v1/runs", tags=["Runs"])


class DiagnosticInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delay_seconds: int = Field(default=0, ge=0, le=30, strict=True)
    outcome: Literal["success", "failure"] = "success"


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    request_id: UUID
    correlation_id: UUID | None = None
    task_type: Literal["diagnostic"] = "diagnostic"
    input: DiagnosticInput = Field(default_factory=DiagnosticInput)


class AcceptedRun(BaseModel):
    run_id: UUID
    status: Status


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    request_id: UUID
    correlation_id: UUID | None
    task_type: Literal["diagnostic"]
    delay_seconds: int
    outcome: Literal["success", "failure"]
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


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int
    run_id: UUID
    attempt_id: UUID | None
    event_type: str
    recorded_at: datetime


def repository(request: Request) -> RunRepository:
    value: RunRepository | None = request.app.state.runs
    if value is None:
        raise HTTPException(503)
    return value


Repo = Annotated[RunRepository, Depends(repository)]


@router.post("", response_model=AcceptedRun, status_code=202)
def create(body: RunInput, repo: Repo) -> AcceptedRun:
    run = repo.create(
        body.project_id,
        body.request_id,
        body.correlation_id,
        body.input.delay_seconds,
        body.input.outcome,
    )
    return AcceptedRun(run_id=run.id, status=run.status)


@router.get("/{run_id}", response_model=RunResponse)
def get(run_id: UUID, repo: Repo) -> RunResponse:
    return RunResponse.model_validate(repo.get(run_id))


@router.get("/{run_id}/events", response_model=list[EventResponse])
def events(
    run_id: UUID,
    repo: Repo,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[EventResponse]:
    return [EventResponse.model_validate(e) for e in repo.events(run_id, after, limit)]
