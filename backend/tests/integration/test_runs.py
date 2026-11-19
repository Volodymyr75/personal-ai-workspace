from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError

from paw.api.app import create_app
from paw.application.execution import execute_diagnostic
from paw.domain.runs import IdempotencyConflict
from paw.infrastructure.db.catalog import PostgresCatalog
from paw.infrastructure.db.connection import DatabaseReadiness
from paw.infrastructure.db.registry import PostgresRegistry
from paw.infrastructure.db.runs import PostgresRuns
from paw.infrastructure.storage.local import LocalBlobStore

pytestmark = pytest.mark.integration


@pytest.fixture
def setup(engine, tmp_path):
    catalog = PostgresCatalog(engine, LocalBlobStore(tmp_path))
    project = catalog.create_project("Synthetic execution tests", "")
    return PostgresRuns(engine), project.id, catalog


def queued(setup, **kwargs):
    repo, project, _ = setup
    return repo.create(
        project,
        kwargs.get("request_id", uuid4()),
        kwargs.get("correlation_id"),
        kwargs.get("delay_seconds", 0),
        kwargs.get("outcome", "success"),
    )


def expire(engine, identity, column="lease_expires_at"):
    assert column in ("lease_expires_at", "attempt_deadline")
    with engine.begin() as c:
        c.execute(
            text(f"UPDATE runs SET {column}=clock_timestamp()-interval '1 second' WHERE id=:id"),
            {"id": identity},
        )


def types(repo, identity):
    return [e.event_type for e in repo.events(identity, 0, 100)]


def test_concurrent_idempotent_enqueue_and_conflict(setup):
    repo, project, _ = setup
    key, correlation = uuid4(), uuid4()
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(
            pool.map(lambda _: queued(setup, request_id=key, correlation_id=correlation), range(4))
        )
    assert len({r.id for r in runs}) == 1
    assert types(repo, runs[0].id) == ["queued"]
    with pytest.raises(IdempotencyConflict):
        repo.create(project, key, correlation, 1, "success")


def test_competing_claimants_only_one_owns_run(setup):
    repo, _, _ = setup
    queued(setup)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: repo.claim(), range(4)))
    claimed = [r for r in claims if r is not None]
    assert len(claimed) == 1
    assert claimed[0].attempt_count == 1
    assert types(repo, claimed[0].id) == ["queued", "started"]


def test_expiry_fences_even_before_reclaim_and_recovery_uses_new_attempt(engine, setup):
    repo, _, _ = setup
    original = queued(setup)
    first = repo.claim()
    expire(engine, original.id)
    assert not repo.finish(first.id, first.attempt_id, None)
    assert not repo.heartbeat(first.id, first.attempt_id)
    second = PostgresRuns(engine).claim()
    assert second.id == first.id and second.attempt_id != first.attempt_id
    assert second.attempt_count == 2
    assert not repo.finish(first.id, first.attempt_id, "diagnostic_failed")
    assert repo.finish(second.id, second.attempt_id, None)
    assert not repo.finish(second.id, second.attempt_id, None)
    assert repo.get(original.id).status == "completed"
    assert types(repo, original.id) == [
        "queued",
        "started",
        "lease_expired",
        "started",
        "completed",
    ]


def test_heartbeat_extends_lease_without_event_noise_and_deadline_is_hard(engine, setup):
    repo, _, _ = setup
    queued(setup)
    run = repo.claim()
    assert repo.heartbeat(run.id, run.attempt_id)
    assert repo.get(run.id).lease_expires_at > run.lease_expires_at
    assert types(repo, run.id) == ["queued", "started"]
    expire(engine, run.id, "attempt_deadline")
    assert not repo.heartbeat(run.id, run.attempt_id)
    assert not repo.finish(run.id, run.attempt_id, None)
    assert repo.claim().attempt_count == 2


def test_repeated_crashes_stop_at_three_attempts(engine, setup):
    repo, _, _ = setup
    run = queued(setup)
    for count in range(1, 4):
        claimed = repo.claim()
        assert claimed.attempt_count == count
        expire(engine, run.id)
    assert repo.claim() is None
    result = repo.get(run.id)
    assert result.status == "failed" and result.error_code == "attempts_exhausted"
    assert result.finished_at is not None
    assert repo.claim() is None
    assert types(repo, run.id)[-1] == "attempts_exhausted"


@pytest.mark.parametrize(
    "outcome,status,error",
    [("success", "completed", None), ("failure", "failed", "diagnostic_failed")],
)
def test_real_executor_persists_truthful_result(setup, outcome, status, error):
    repo, _, _ = setup
    queued(setup, outcome=outcome)
    run = repo.claim()
    assert execute_diagnostic(repo, run, Event())
    result = repo.get(run.id)
    assert result.status == status and result.error_code == error
    assert (result.output is not None) == (outcome == "success")
    assert repo.claim() is None


def test_interrupted_executor_leaves_recoverable_lease(engine, setup):
    repo, _, _ = setup
    queued(setup, delay_seconds=30)
    run = repo.claim()
    stop = Event()
    stop.set()
    assert not execute_diagnostic(repo, run, stop)
    assert repo.get(run.id).status == "running"
    expire(engine, run.id)
    assert repo.claim().attempt_count == 2


@pytest.mark.parametrize("operation", ["create", "claim", "finish"])
def test_event_failure_rolls_back_state(engine, setup, operation):
    repo, _, _ = setup
    run = None
    if operation != "create":
        run = queued(setup)
    if operation == "finish":
        run = repo.claim()

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO run_events" in statement:
            raise SQLAlchemyError("private detail")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SQLAlchemyError):
            if operation == "create":
                queued(setup)
            elif operation == "claim":
                repo.claim()
            else:
                repo.finish(run.id, run.attempt_id, None)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    if operation == "create":
        assert repo.claim() is None
    else:
        assert repo.get(run.id).status == ("queued" if operation == "claim" else "running")


def test_api_contract_and_restart_preserve_queued_run(engine, setup):
    repo, project, catalog = setup
    body = {
        "project_id": str(project),
        "request_id": str(uuid4()),
        "task_type": "diagnostic",
        "input": {"delay_seconds": 0, "outcome": "success"},
    }
    with TestClient(create_app(DatabaseReadiness(engine), catalog, repo)) as client:
        response = client.post("/api/v1/runs", json=body)
        assert response.status_code == 202
        identity = response.json()["run_id"]
        assert client.post("/api/v1/runs", json=body).json() == response.json()
        changed = {**body, "input": {"delay_seconds": 1}}
        assert client.post("/api/v1/runs", json=changed).status_code == 409
        for change in (
            {"task_type": "agent:data_analyst"},
            {"input": {"delay_seconds": 31}},
            {"input": {"shell": "echo no"}},
            {"input": {"delay_seconds": True}},
        ):
            assert client.post("/api/v1/runs", json={**body, **change}).status_code == 422
        assert (
            client.post("/api/v1/runs", json={**body, "project_id": str(uuid4())}).status_code
            == 404
        )
    reopened = PostgresRuns(engine)
    with TestClient(create_app(DatabaseReadiness(engine), catalog, reopened)) as client:
        assert client.get("/api/v1/runs/" + identity).json()["status"] == "queued"
        claim = reopened.claim()
        assert execute_diagnostic(reopened, claim, Event())
        assert client.get("/api/v1/runs/" + identity).json()["status"] == "completed"
        page = client.get(f"/api/v1/runs/{identity}/events?limit=1").json()
        remaining = client.get(f"/api/v1/runs/{identity}/events?after={page[0]['sequence']}").json()
        assert [e["event_type"] for e in remaining] == ["started", "completed"]
        assert client.get("/api/v1/runs/" + str(uuid4())).status_code == 404
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM system_events")).scalar_one() == 0


def test_worker_registration_is_idempotent_and_uses_real_server_time(engine):
    registry = PostgresRegistry(engine)
    assert registry.bootstrap() == 3
    with ThreadPoolExecutor(max_workers=3) as pool:
        added = list(pool.map(lambda _: registry.register_worker(), range(3)))
    assert sum(added) == 2
    assert registry.bootstrap() == 0
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM system_events")).scalar_one() == 5
        assert (
            c.execute(
                text("SELECT count(*) FROM system_events WHERE source='service:worker'")
            ).scalar_one()
            == 2
        )
