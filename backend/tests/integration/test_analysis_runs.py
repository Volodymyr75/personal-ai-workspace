import json
from hashlib import sha256
from threading import Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError

from paw.api.app import create_app
from paw.application.files import upload_csv
from paw.domain.analysis import AnalysisSpec, Bundle
from paw.infrastructure.db.catalog import PostgresCatalog
from paw.infrastructure.db.connection import DatabaseReadiness
from paw.infrastructure.db.runs import PostgresRuns
from paw.infrastructure.execution.analysis import execute_analysis
from paw.infrastructure.storage.local import LocalBlobStore
from paw.infrastructure.storage.source import StoredSource

pytestmark = pytest.mark.integration
CSV = b"group,value\na,2\na,3\nb,4\n"


@pytest.fixture
def setup(engine, tmp_path):
    blobs = LocalBlobStore(tmp_path / "files")
    catalog = PostgresCatalog(engine, blobs)
    project = catalog.create_project("Synthetic analysis", "")
    source = upload_csv(catalog, project.id, "example.csv", CSV, ",")
    artifacts = LocalBlobStore(tmp_path / "artifacts", "bin")
    repo = PostgresRuns(engine, artifacts)
    return repo, catalog, source, StoredSource(catalog, blobs), artifacts


def enqueue(setup):
    repo, _, source, _, _ = setup
    return repo.create(
        source.project_id,
        uuid4(),
        None,
        0,
        "success",
        source.id,
        AnalysisSpec(("value",), "value", "group"),
    )


def expire(engine, identity):
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE runs SET lease_expires_at=clock_timestamp()-interval '1 second' "
                "WHERE id=:id"
            ),
            {"id": identity},
        )


def test_real_child_analysis_and_artifact_api_survive_reopen(engine, setup):
    repo, catalog, source, reader, blobs = setup
    original = enqueue(setup)
    claim = repo.claim()
    assert execute_analysis(repo, reader, claim, Event())
    result = repo.get(original.id)
    assert result.status == "completed"
    report_id = UUID(result.output["report_artifact_id"])
    metadata, data = repo.artifact(report_id)
    assert metadata.run_id == original.id and metadata.attempt_id == claim.attempt_id
    assert metadata.sha256 == sha256(data).hexdigest()
    report = json.loads(data)
    assert report["summary"]["value"]["sum"] == 9
    assert report["groups"][0]["sums"]["value"] == 5
    reopened = PostgresRuns(engine, blobs)
    reopened.reconcile_artifacts()
    with TestClient(create_app(DatabaseReadiness(engine), catalog, reopened)) as client:
        response = client.get("/api/v1/artifacts/" + str(report_id))
        assert response.status_code == 200 and response.json() == report
        chart = client.get("/api/v1/artifacts/" + result.output["chart_artifact_id"])
        assert chart.headers["content-type"] == "image/png"
        assert chart.content.startswith(b"\x89PNG")
        assert "attachment" in chart.headers["content-disposition"]
        assert client.get("/api/v1/artifacts/" + str(uuid4())).status_code == 404
    assert len(blobs.ids()) == 2


def test_api_rejects_cross_project_file_and_invalid_specs(engine, setup):
    repo, catalog, source, _, _ = setup
    body = {
        "project_id": str(source.project_id),
        "request_id": str(uuid4()),
        "task_type": "csv_analysis",
        "input": {
            "file_id": str(source.id),
            "numeric_columns": ["value"],
            "chart_column": "value",
            "group_by": "group",
        },
    }
    with TestClient(create_app(DatabaseReadiness(engine), catalog, repo)) as client:
        response = client.post("/api/v1/runs", json=body)
        assert response.status_code == 202
        assert client.post("/api/v1/runs", json=body).json() == response.json()
        other = catalog.create_project("Other", "")
        assert (
            client.post("/api/v1/runs", json={**body, "project_id": str(other.id)}).status_code
            == 404
        )
        for change in (
            {"numeric_columns": ["value", "value"]},
            {"chart_column": "unknown"},
            {"group_by": "value"},
            {"formula": "print(1)"},
            {"ratios": [{"name": "r", "numerator": "value", "denominator": "unknown"}]},
        ):
            assert (
                client.post(
                    "/api/v1/runs", json={**body, "input": {**body["input"], **change}}
                ).status_code
                == 422
            )
        assert (
            client.post(
                "/api/v1/runs", json={**body, "input": {**body["input"], "group_by": None}}
            ).status_code
            == 409
        )


def test_expired_attempt_cannot_publish_or_overwrite(engine, setup):
    repo, _, _, _, blobs = setup
    enqueue(setup)
    first = repo.claim()
    expire(engine, first.id)
    bundle = Bundle(b"{}", b"png-test")
    assert not repo.publish(first.id, first.attempt_id, bundle)
    assert not blobs.ids()
    second = repo.claim()
    assert repo.publish(second.id, second.attempt_id, bundle)
    retained = blobs.ids()
    assert not repo.publish(first.id, first.attempt_id, bundle)
    assert not repo.publish(second.id, second.attempt_id, bundle)
    assert blobs.ids() == retained


@pytest.mark.parametrize("failure", ["database", "disk"])
def test_failed_publication_rolls_back_result_and_cleans_blobs(engine, setup, monkeypatch, failure):
    repo, _, _, _, blobs = setup
    enqueue(setup)
    run = repo.claim()

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO run_events" in statement:
            raise SQLAlchemyError("private error")

    real_put = blobs.put
    calls = 0

    def broken_put(identity, data):
        nonlocal calls
        calls += 1
        real_put(identity, data)
        if calls == 2:
            raise OSError("private path")

    if failure == "database":
        event.listen(engine, "before_cursor_execute", fail)
    else:
        monkeypatch.setattr(blobs, "put", broken_put)
    try:
        with pytest.raises((SQLAlchemyError, OSError)):
            repo.publish(run.id, run.attempt_id, Bundle(b"{}", b"png-test"))
    finally:
        if failure == "database":
            event.remove(engine, "before_cursor_execute", fail)
    assert not blobs.ids()
    assert repo.get(run.id).status == "running"
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM artifacts")).scalar_one() == 0


def test_orphan_recovery_preserves_committed_and_detects_corruption(setup):
    repo, _, _, _, blobs = setup
    enqueue(setup)
    run = repo.claim()
    repo.publish(run.id, run.attempt_id, Bundle(b"{}", b"png-test"))
    keep = blobs.ids()
    blobs.put(uuid4(), b"orphan")
    repo.reconcile_artifacts()
    assert blobs.ids() == keep
    identity = UUID(repo.get(run.id).output["report_artifact_id"])
    blobs.put(identity, b"changed")
    with pytest.raises(OSError):
        repo.artifact(identity)


def test_missing_source_and_analysis_failure_are_terminal(setup):
    repo, catalog, source, reader, blobs = setup
    enqueue(setup)
    run = repo.claim()
    catalog.storage.delete(source.id)
    assert execute_analysis(repo, reader, run, Event())
    assert repo.get(run.id).error_code == "source_unavailable"
    assert not blobs.ids()


def test_child_timeout_is_terminal_and_does_not_publish(setup, monkeypatch):
    repo, _, _, reader, blobs = setup
    enqueue(setup)
    run = repo.claim()
    monkeypatch.setattr("paw.infrastructure.execution.analysis.ANALYSIS_SECONDS", 0)
    assert execute_analysis(repo, reader, run, Event())
    assert repo.get(run.id).error_code == "analysis_timeout"
    assert not blobs.ids()


def test_interruption_does_not_publish(setup):
    repo, _, _, reader, blobs = setup
    enqueue(setup)
    run = repo.claim()
    stop = Event()
    stop.set()
    assert not execute_analysis(repo, reader, run, stop)
    assert repo.get(run.id).status == "running"
    assert not blobs.ids()


def test_lease_lost_during_blob_writes_rolls_back_publication(setup, monkeypatch):
    repo, _, _, _, blobs = setup
    enqueue(setup)
    run = repo.claim()
    real_owned = repo._owned
    checks = 0

    def loses_ownership(c, identity, attempt):
        nonlocal checks
        checks += 1
        return real_owned(c, identity, attempt) and checks < 3

    monkeypatch.setattr(repo, "_owned", loses_ownership)
    assert not repo.publish(run.id, run.attempt_id, Bundle(b"{}", b"png-test"))
    assert checks == 3
    assert not blobs.ids()
    assert repo.get(run.id).status == "running"
    assert repo.get(run.id).output is None
