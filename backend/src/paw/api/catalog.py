from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from paw.application.files import upload_csv
from paw.domain.files import MAX_FILE_BYTES, Catalog, InputError

router = APIRouter(prefix="/api/v1")


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str
    created_at: datetime


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    original_name: str
    size_bytes: int
    sha256: str
    row_count: int
    column_count: int
    delimiter: str
    created_at: datetime
    mime_type: Literal["text/csv"] = "text/csv"


def catalog(request: Request) -> Catalog:
    value: Catalog | None = request.app.state.catalog
    if value is None:
        raise HTTPException(503)
    return value


Repo = Annotated[Catalog, Depends(catalog)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectInput, repo: Repo) -> ProjectResponse:
    return ProjectResponse.model_validate(repo.create_project(body.name, body.description))


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(repo: Repo, limit: Limit = 50, offset: Offset = 0) -> list[ProjectResponse]:
    return [ProjectResponse.model_validate(p) for p in repo.list_projects(limit, offset)]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, repo: Repo) -> ProjectResponse:
    return ProjectResponse.model_validate(repo.get_project(project_id))


@router.get("/projects/{project_id}/files", response_model=list[FileResponse])
def list_files(
    project_id: UUID, repo: Repo, limit: Limit = 50, offset: Offset = 0
) -> list[FileResponse]:
    return [FileResponse.model_validate(f) for f in repo.list_files(project_id, limit, offset)]


@router.get("/files/{file_id}", response_model=FileResponse)
def get_file(file_id: UUID, repo: Repo) -> FileResponse:
    return FileResponse.model_validate(repo.get_file(file_id))


@router.post(
    "/files",
    response_model=FileResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "additionalProperties": False,
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        },
    },
)
async def upload(
    request: Request, project_id: UUID, repo: Repo, delimiter: Literal[",", ";"] = ","
) -> FileResponse:
    if request.headers.get("content-type", "").split(";")[0].lower() != "multipart/form-data":
        raise HTTPException(415)
    async with request.form(max_files=1, max_fields=0, max_part_size=65536) as form:
        items = list(form.multi_items())
        if len(items) != 1 or items[0][0] != "file" or not isinstance(items[0][1], UploadFile):
            raise InputError("invalid_upload")
        file = items[0][1]
        if file.content_type not in (
            None,
            "text/csv",
            "application/csv",
            "text/plain",
            "application/octet-stream",
            "application/vnd.ms-excel",
        ):
            raise HTTPException(415)
        data = await file.read(MAX_FILE_BYTES + 1)
        saved = await run_in_threadpool(
            upload_csv, repo, project_id, file.filename or "", data, delimiter
        )
    return FileResponse.model_validate(saved)
