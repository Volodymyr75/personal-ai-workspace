from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from paw.domain.analysis import AnalysisSpec, Ratio
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


class RatioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    numerator: str = Field(min_length=1, max_length=256)
    denominator: str = Field(min_length=1, max_length=256)
    scale: Literal[1, 100] = 1


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: UUID
    numeric_columns: list[str] = Field(min_length=1, max_length=8)
    group_by: str | None = Field(default=None, min_length=1, max_length=256)
    chart_column: str = Field(min_length=1, max_length=256)
    ratios: list[RatioInput] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def selected_columns(self) -> "AnalysisInput":
        columns = set(self.numeric_columns)
        if len(columns) != len(self.numeric_columns) or any(not c or len(c) > 256 for c in columns):
            raise ValueError("Invalid numeric selection")
        if self.chart_column not in columns or self.group_by in columns:
            raise ValueError("Invalid chart/group selection")
        if len({r.name for r in self.ratios}) != len(self.ratios):
            raise ValueError("Duplicate ratio name")
        if any(r.numerator not in columns or r.denominator not in columns for r in self.ratios):
            raise ValueError("Ratio columns must be selected")
        return self


class AnalysisRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    request_id: UUID
    correlation_id: UUID | None = None
    task_type: Literal["csv_analysis"]
    input: AnalysisInput


class AcceptedRun(BaseModel):
    run_id: UUID
    status: Status


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    request_id: UUID
    correlation_id: UUID | None
    task_type: Literal["diagnostic", "csv_analysis"]
    file_id: UUID | None
    analysis: AnalysisSpec | None
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
def create(body: RunInput | AnalysisRunInput, repo: Repo) -> AcceptedRun:
    if isinstance(body, AnalysisRunInput):
        selected = body.input
        spec = AnalysisSpec(
            tuple(selected.numeric_columns),
            selected.chart_column,
            selected.group_by,
            tuple(Ratio(r.name, r.numerator, r.denominator, r.scale) for r in selected.ratios),
        )
        run = repo.create(
            body.project_id,
            body.request_id,
            body.correlation_id,
            0,
            "success",
            selected.file_id,
            spec,
        )
    else:
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


artifacts_router = APIRouter(prefix="/api/v1/artifacts", tags=["Artifacts"])


@artifacts_router.get("/{artifact_id}", response_class=Response)
def download(artifact_id: UUID, repo: Repo) -> Response:
    metadata, data = repo.artifact(artifact_id)
    extension = "json" if metadata.kind == "report" else "png"
    filename = f"{metadata.kind}-{metadata.id}.{extension}"
    return Response(
        data,
        media_type=metadata.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
