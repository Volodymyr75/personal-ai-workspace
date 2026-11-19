from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, Engine, insert, select, text

from paw.domain.registry import API, API_DATABASE, DATABASE, safe_metadata
from paw.infrastructure.db.tables import edges, events, nodes

# Serialize the small registry mutation path, including all bootstrap retries.
# Use the same lock in future lifecycle mutation methods to preserve event order.
REGISTRY_LOCK = 72841001


def append_registration(
    connection: Connection,
    event_type: str,
    entity_key: str,
    occurred_at: datetime,
    after_state: dict[str, Any],
) -> None:
    connection.execute(
        insert(events).values(
            id=uuid4(),
            event_type=event_type,
            entity_key=entity_key,
            source="command:bootstrap",
            schema_version=1,
            occurred_at=occurred_at,
            idempotency_key=f"registration:{entity_key}",
            payload_safe_json=after_state,
        )
    )


def assert_registration_exists(connection: Connection, key: str) -> None:
    event = connection.execute(
        select(events.c.id).where(events.c.idempotency_key == f"registration:{key}")
    ).scalar_one_or_none()
    if event is None:
        # Do not invent history for a pre-existing, uninstrumented row.
        raise ValueError("Registry history is inconsistent; explicit correction required")


class PostgresRegistry:
    def __init__(self, engine: Engine):
        self.engine = engine

    def bootstrap(self) -> int:
        added = 0
        with self.engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": REGISTRY_LOCK})
            now: datetime = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
            for node in (API, DATABASE):
                if connection.execute(select(nodes.c.key).where(nodes.c.key == node.key)).first():
                    assert_registration_exists(connection, node.key)
                    continue
                safe = safe_metadata({"runtime": node.runtime})
                state = dict(
                    key=node.key,
                    kind=node.kind,
                    display_name=node.display_name,
                    lifecycle_state="active",
                    registered_at=now,
                    retired_at=None,
                    metadata_json=safe,
                )
                connection.execute(insert(nodes).values(**state))
                append_registration(
                    connection,
                    f"{node.kind}.registered",
                    node.key,
                    now,
                    {**state, "registered_at": now.isoformat()},
                )
                added += 1
            edge = API_DATABASE
            if connection.execute(select(edges.c.key).where(edges.c.key == edge.key)).first():
                assert_registration_exists(connection, edge.key)
            else:
                state = dict(
                    key=edge.key,
                    source_key=edge.source_key,
                    target_key=edge.target_key,
                    relation=edge.relation,
                    registered_at=now,
                    retired_at=None,
                )
                connection.execute(insert(edges).values(**state))
                append_registration(
                    connection,
                    "link.added",
                    edge.key,
                    now,
                    {**state, "registered_at": now.isoformat()},
                )
                added += 1
        return added
