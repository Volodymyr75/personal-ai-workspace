import logging
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, insert, select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError

from paw.domain.files import BlobStore, CsvInfo, NotFound, Project, StoredFile
from paw.infrastructure.db.tables import files, projects

UPLOAD_LOCK = 72841002
DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")
logger = logging.getLogger("paw")


def project_record(row: RowMapping) -> Project:
    return Project(row["id"], row["name"], row["description"], row["created_at"])


def file_record(row: RowMapping) -> StoredFile:
    return StoredFile(**{key: row[key] for key in StoredFile.__dataclass_fields__})


class PostgresCatalog:
    def __init__(self, engine: Engine, storage: BlobStore):
        self.engine = engine
        self.storage = storage

    def create_project(self, name: str, description: str) -> Project:
        with self.engine.begin() as c:
            row = (
                c.execute(
                    insert(projects)
                    .values(
                        id=uuid4(),
                        workspace_id=DEFAULT_WORKSPACE,
                        name=name,
                        description=description,
                    )
                    .returning(projects)
                )
                .mappings()
                .one()
            )
        return project_record(row)

    def list_projects(self, limit: int, offset: int) -> list[Project]:
        with self.engine.connect() as c:
            rows = (
                c.execute(
                    select(projects)
                    .order_by(projects.c.created_at, projects.c.id)
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return [project_record(row) for row in rows]

    def get_project(self, project_id: UUID) -> Project:
        with self.engine.connect() as c:
            row = c.execute(select(projects).where(projects.c.id == project_id)).mappings().first()
        if row is None:
            raise NotFound()
        return project_record(row)

    def get_file(self, file_id: UUID) -> StoredFile:
        with self.engine.connect() as c:
            row = c.execute(select(files).where(files.c.id == file_id)).mappings().first()
        if row is None:
            raise NotFound()
        return file_record(row)

    def list_files(self, project_id: UUID, limit: int, offset: int) -> list[StoredFile]:
        self.get_project(project_id)
        with self.engine.connect() as c:
            rows = (
                c.execute(
                    select(files)
                    .where(files.c.project_id == project_id)
                    .order_by(files.c.created_at, files.c.id)
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return [file_record(row) for row in rows]

    def _reconcile(self, c: Connection) -> None:
        # Called only while holding UPLOAD_LOCK, so no active upload's staging file is removed.
        referenced = set(c.execute(select(files.c.id)).scalars())
        for identity in self.storage.ids() - referenced:
            self.storage.delete(identity)
        self.storage.clear_temporary()

    def reconcile(self) -> None:
        with self.engine.begin() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": UPLOAD_LOCK})
            self._reconcile(c)

    def save_file(self, project_id: UUID, name: str, data: bytes, info: CsvInfo) -> StoredFile:
        identity = uuid4()
        try:
            with self.engine.begin() as c:
                c.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": UPLOAD_LOCK})
                self._reconcile(c)
                if (
                    c.execute(select(projects.c.id).where(projects.c.id == project_id)).first()
                    is None
                ):
                    raise NotFound()
                self.storage.put(identity, data)
                row = (
                    c.execute(
                        insert(files)
                        .values(
                            id=identity,
                            project_id=project_id,
                            original_name=name,
                            storage_key=f"{identity}.csv",
                            mime_type="text/csv",
                            size_bytes=info.size_bytes,
                            sha256=info.sha256,
                            row_count=info.row_count,
                            column_count=info.column_count,
                            delimiter=info.delimiter,
                        )
                        .returning(files)
                    )
                    .mappings()
                    .one()
                )
            return file_record(row)
        except Exception:
            # COMMIT failure can be ambiguous. Re-read committed state before deleting any blob.
            # If DB is unavailable, leave it for startup/next-upload reconciliation.
            try:
                self.reconcile()
            except (SQLAlchemyError, OSError):
                logger.warning("upload_cleanup_deferred")
            raise
