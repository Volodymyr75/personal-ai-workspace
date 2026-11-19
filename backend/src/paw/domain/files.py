import csv
import io
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 200
MAX_CELL_CHARS = 32_768


class InputError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class NotFound(Exception):
    pass


@dataclass(frozen=True)
class CsvInfo:
    size_bytes: int
    sha256: str
    row_count: int
    column_count: int
    delimiter: str


@dataclass(frozen=True)
class Project:
    id: UUID
    name: str
    description: str
    created_at: datetime


@dataclass(frozen=True)
class StoredFile:
    id: UUID
    project_id: UUID
    original_name: str
    size_bytes: int
    sha256: str
    row_count: int
    column_count: int
    delimiter: str
    created_at: datetime


class BlobStore(Protocol):
    def put(self, file_id: UUID, data: bytes) -> None: ...
    def delete(self, file_id: UUID) -> None: ...
    def ids(self) -> set[UUID]: ...
    def clear_temporary(self) -> None: ...


class Catalog(Protocol):
    def create_project(self, name: str, description: str) -> Project: ...
    def list_projects(self, limit: int, offset: int) -> list[Project]: ...
    def get_project(self, project_id: UUID) -> Project: ...
    def save_file(self, project_id: UUID, name: str, data: bytes, info: CsvInfo) -> StoredFile: ...
    def get_file(self, file_id: UUID) -> StoredFile: ...
    def list_files(self, project_id: UUID, limit: int, offset: int) -> list[StoredFile]: ...


def validate_name(name: str) -> str:
    # Reject paths rather than normalizing an attacker-supplied path into a storage name.
    if (
        not name
        or len(name) > 255
        or any(c in name for c in ("/", "\\", ":"))
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
        or not name.lower().endswith(".csv")
    ):
        raise InputError("invalid_filename")
    return name


def inspect_csv(data: bytes, delimiter: str = ",") -> CsvInfo:
    if len(data) > MAX_FILE_BYTES:
        raise InputError("file_too_large")
    if delimiter not in (",", ";"):
        raise InputError("invalid_delimiter")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("invalid_encoding") from None
    if any(ord(c) < 32 and c not in "\r\n\t" for c in content) or "\x7f" in content:
        raise InputError("invalid_csv")
    reader = csv.reader(io.StringIO(content, newline=""), delimiter=delimiter, strict=True)
    try:
        header = next(reader, [])
        normalized = [x.strip() for x in header]
        if not header or any(not x for x in normalized) or len(set(normalized)) != len(header):
            raise InputError("invalid_headers")
        if len(header) > MAX_COLUMNS:
            raise InputError("too_many_columns")
        if any(len(x) > 256 for x in header):
            raise InputError("header_too_long")
        count = 0
        for row in reader:
            if len(row) != len(header):
                raise InputError("inconsistent_columns")
            if any(len(x) > MAX_CELL_CHARS for x in row):
                raise InputError("cell_too_large")
            count += 1
            if count > MAX_ROWS:
                raise InputError("too_many_rows")
        if count == 0:
            raise InputError("empty_csv")
    except csv.Error:
        raise InputError("invalid_csv") from None
    return CsvInfo(len(data), sha256(data).hexdigest(), count, len(header), delimiter)
