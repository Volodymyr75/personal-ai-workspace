from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError

from paw.api.app import create_app
from paw.application.files import upload_csv
from paw.infrastructure.db.catalog import PostgresCatalog
from paw.infrastructure.db.connection import DatabaseReadiness
from paw.infrastructure.db.tables import events, files
from paw.infrastructure.storage.local import LocalBlobStore

pytestmark = pytest.mark.integration
CSV = b"name,value\r\nalpha,10\r\nbeta,20\r\n"


@pytest.fixture
def catalog(engine, tmp_path):
    return PostgresCatalog(engine, LocalBlobStore(tmp_path))


@pytest.fixture
def client(engine, catalog):
    with TestClient(create_app(DatabaseReadiness(engine), catalog)) as c:
        yield c


def make_project(client, name="Synthetic project"):
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, project, data=CSV, filename="example.csv", **kwargs):
    return client.post(
        "/api/v1/files",
        params={"project_id": project},
        files={"file": (filename, data, "text/csv")},
        **kwargs,
    )


def test_project_and_upload_persist_without_leaking_storage_paths(
    client, engine, catalog, tmp_path
):
    project = make_project(client)
    other = make_project(client, "Other")
    assert len(client.get("/api/v1/projects?limit=1").json()) == 1
    assert client.get(f"/api/v1/projects/{project}").json()["name"] == "Synthetic project"
    response = upload(client, project)
    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == project
    assert body["row_count"] == 2
    assert body["column_count"] == 2
    assert "storage_key" not in body and "stored_path" not in body
    assert (tmp_path / f"{body['id']}.csv").read_bytes() == CSV
    # New service/repository instances simulate re-opening persisted DB and filesystem state.
    reopened = PostgresCatalog(engine, LocalBlobStore(tmp_path))
    reopened.reconcile()
    with TestClient(create_app(DatabaseReadiness(engine), reopened)) as restarted:
        assert restarted.get(f"/api/v1/files/{body['id']}").json() == body
        assert len(restarted.get(f"/api/v1/projects/{project}/files").json()) == 1
        assert restarted.get(f"/api/v1/projects/{other}/files").json() == []
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(events)).scalar_one() == 0
    assert len(catalog.storage.ids()) == 1


@pytest.mark.parametrize(
    "data,filename,status",
    [
        (b"bad,\n1,2", "x.csv", 422),
        (CSV, "../escape.csv", 422),
        (CSV, "x.xlsx", 422),
        (b"\xff", "x.csv", 422),
        (b"x" * (10 * 1024 * 1024 + 1), "x.csv", 413),
    ],
)
def test_rejected_upload_leaves_no_files_or_metadata(
    client, catalog, engine, tmp_path, data, filename, status
):
    response = upload(client, make_project(client), data, filename)
    assert response.status_code == status
    assert not list(tmp_path.iterdir())
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(files)).scalar_one() == 0


def test_missing_project_and_invalid_requests(client, tmp_path):
    assert upload(client, str(uuid4())).status_code == 404
    assert client.get("/api/v1/files/" + str(uuid4())).status_code == 404
    assert client.post("/api/v1/projects", json={"name": "   "}).status_code == 422
    assert client.get("/api/v1/projects?limit=101").status_code == 422
    assert client.post("/api/v1/files?project_id=invalid", content=CSV).status_code == 422
    assert not list(tmp_path.iterdir())


def test_multipart_only_one_file_and_no_extra_fields(client, tmp_path):
    project = make_project(client)
    path = f"/api/v1/files?project_id={project}"
    assert client.post(path, content=CSV, headers={"content-type": "text/csv"}).status_code == 415
    assert (
        client.post(path, files=[("file", ("a.csv", CSV)), ("file", ("b.csv", CSV))]).status_code
        == 400
    )
    assert (
        client.post(path, files={"file": ("a.csv", CSV)}, data={"extra": "secret"}).status_code
        == 400
    )
    assert (
        client.post(
            path, content=b"broken", headers={"content-type": "multipart/form-data"}
        ).status_code
        == 400
    )
    assert not list(tmp_path.iterdir())


def test_database_failure_removes_blob_and_redacts_errors(client, engine, tmp_path, caplog):
    project = make_project(client)

    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO files"):
            raise SQLAlchemyError("private dataset and password must not leak")

    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        response = upload(client, project)
        assert response.status_code == 503
        assert response.json() == {"code": "storage_unavailable"}
        assert not list(tmp_path.iterdir())
        assert "private dataset" not in caplog.text
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)


def test_disk_failure_removes_partial_file(client, catalog, tmp_path, monkeypatch):
    project = make_project(client)

    def fail_put(identity, data):
        (tmp_path / f"{identity}.part").write_bytes(b"partial")
        raise OSError("private filesystem detail")

    monkeypatch.setattr(catalog.storage, "put", fail_put)
    response = upload(client, project)
    assert response.status_code == 503
    assert not list(tmp_path.iterdir())


def test_recovery_cleans_crash_leftovers_but_preserves_committed_blobs(client, catalog, tmp_path):
    body = upload(client, make_project(client)).json()
    orphan = uuid4()
    catalog.storage.put(orphan, CSV)
    (tmp_path / f"{uuid4()}.part").write_bytes(b"incomplete")
    (tmp_path / "unrelated.txt").write_text("not owned by the upload store")
    catalog.reconcile()
    assert catalog.storage.ids() == {UUID(body["id"])}
    assert list(tmp_path.glob("*.part")) == []
    assert (tmp_path / "unrelated.txt").exists()


def test_concurrent_uploads_do_not_remove_each_others_files(catalog, tmp_path):
    project = catalog.create_project("Concurrent", "")
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(
            pool.map(lambda _: upload_csv(catalog, project.id, "same.csv", CSV, ","), range(2))
        )
    assert len({r.id for r in result}) == 2
    assert catalog.storage.ids() == {r.id for r in result}
    assert all((tmp_path / f"{r.id}.csv").read_bytes() == CSV for r in result)


def test_semicolon_bom_upload(client):
    response = client.post(
        "/api/v1/files",
        params={"project_id": make_project(client), "delimiter": ";"},
        files={"file": ("words.csv", "\ufeffword;meaning\ntere;привіт\n".encode(), "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["column_count"] == 2
    assert response.json()["delimiter"] == ";"
