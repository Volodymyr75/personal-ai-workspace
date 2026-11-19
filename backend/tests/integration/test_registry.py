from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from paw.api.app import create_app
from paw.infrastructure.db.connection import DatabaseReadiness
from paw.infrastructure.db.registry import PostgresRegistry
from paw.infrastructure.db.tables import edges, events, nodes

pytestmark = pytest.mark.integration


def snapshot(engine):
    with engine.connect() as c:
        return [
            list(c.execute(select(t).order_by(t.c.key if "key" in t.c else t.c.sequence)))
            for t in (nodes, edges, events)
        ]


def test_bootstrap_persists_history_once_and_in_order(engine):
    registry = PostgresRegistry(engine)
    before = datetime.now(UTC)
    assert registry.bootstrap() == 3
    first = snapshot(engine)
    assert registry.bootstrap() == 0
    assert snapshot(engine) == first
    assert [len(rows) for rows in first] == [2, 1, 3]
    with engine.connect() as c:
        rows = c.execute(select(events).order_by(events.c.sequence)).mappings().all()
    assert [r["event_type"] for r in rows] == [
        "service.registered",
        "storage.registered",
        "link.added",
    ]
    assert [r["sequence"] for r in rows] == sorted(r["sequence"] for r in rows)
    for row in rows:
        assert before <= row["recorded_at"] <= datetime.now(UTC)
        assert row["recorded_at"].utcoffset().total_seconds() == 0
        assert row["payload_safe_json"]["key"] == row["entity_key"]
        assert "registered_at" in row["payload_safe_json"]
    assert rows[2]["payload_safe_json"]["source_key"] == "service:api"
    assert rows[2]["payload_safe_json"]["target_key"] == "storage:postgres"
    assert set(rows[0]["payload_safe_json"]["metadata_json"]) == {"runtime"}


def test_concurrent_bootstrap_has_no_duplicate_history(engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: PostgresRegistry(engine).bootstrap(), range(4)))
    assert sorted(results) == [0, 0, 0, 3]
    assert [len(rows) for rows in snapshot(engine)] == [2, 1, 3]


def test_event_failure_rolls_back_projection_and_all_events(engine):
    from paw.infrastructure.db import registry as module

    original = module.append_registration
    calls = 0

    def fail_last(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError("injected failure")
        return original(*args, **kwargs)

    with patch.object(module, "append_registration", side_effect=fail_last):
        with pytest.raises(ValueError):
            PostgresRegistry(engine).bootstrap()
    assert [len(rows) for rows in snapshot(engine)] == [0, 0, 0]
    assert PostgresRegistry(engine).bootstrap() == 3


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE system_events SET source='modified'",
        "DELETE FROM system_events",
        "TRUNCATE system_events",
    ],
)
def test_history_is_append_only(engine, statement):
    PostgresRegistry(engine).bootstrap()
    original = snapshot(engine)
    with pytest.raises(DBAPIError, match="append-only"):
        with engine.begin() as c:
            c.execute(text(statement))
    assert snapshot(engine) == original


def test_duplicate_idempotency_key_is_rejected(engine):
    PostgresRegistry(engine).bootstrap()
    with engine.connect() as c:
        row = dict(c.execute(select(events)).mappings().first())
    del row["sequence"]
    row["id"] = uuid4()
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(events).values(**row))


def test_recorded_at_cannot_be_backdated_by_insert(engine):
    with engine.begin() as c:
        before = c.execute(text("SELECT clock_timestamp()")).scalar_one()
        row = c.execute(
            insert(events)
            .values(
                id=uuid4(),
                event_type="milestone.reached",
                entity_key="milestone:test",
                source="test",
                schema_version=1,
                occurred_at=datetime(2000, 1, 1, tzinfo=UTC),
                recorded_at=datetime(2000, 1, 1, tzinfo=UTC),
                payload_safe_json={},
            )
            .returning(events.c.recorded_at)
        ).scalar_one()
    assert row >= before


def test_readiness_reads_actual_schema_and_never_appends_events(engine):
    readiness = DatabaseReadiness(engine)
    with TestClient(create_app(readiness)) as client:
        assert client.get("/api/v1/ready").status_code == 200
        with engine.connect() as c:
            assert c.execute(select(func.count()).select_from(events)).scalar_one() == 0
        with engine.begin() as c:
            c.execute(text("UPDATE alembic_version SET version_num='incompatible'"))
        assert client.get("/api/v1/ready").status_code == 503
        assert client.get("/api/v1/health").status_code == 200


def test_bootstrap_refuses_missing_history_instead_of_backfilling(engine):
    with engine.begin() as c:
        c.execute(
            insert(nodes).values(
                key="service:api",
                kind="service",
                display_name="API",
                lifecycle_state="active",
                registered_at=datetime.now(UTC),
                metadata_json={},
            )
        )
    with pytest.raises(ValueError, match="inconsistent"):
        PostgresRegistry(engine).bootstrap()
    assert [len(rows) for rows in snapshot(engine)] == [1, 0, 0]
