import json
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping

from paw.domain.files import NotFound
from paw.domain.runs import (
    LEASE_SECONDS,
    MAX_ATTEMPT_SECONDS,
    MAX_ATTEMPTS,
    IdempotencyConflict,
    Run,
    RunEvent,
)


def record(row: RowMapping) -> Run:
    return Run(**dict(row))


def event(c: Connection, run_id: UUID, attempt_id: UUID | None, kind: str) -> None:
    c.execute(
        text("""INSERT INTO run_events (id, run_id, attempt_id, event_type)
        VALUES (:id, :run, :attempt, :kind)"""),
        dict(id=uuid4(), run=run_id, attempt=attempt_id, kind=kind),
    )


class PostgresRuns:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create(
        self,
        project_id: UUID,
        request_id: UUID,
        correlation_id: UUID | None,
        delay_seconds: int,
        outcome: str,
    ) -> Run:
        with self.engine.begin() as c:
            if not c.execute(
                text("SELECT id FROM projects WHERE id=:id"), {"id": project_id}
            ).first():
                raise NotFound()
            row = (
                c.execute(
                    text("""INSERT INTO runs
                (id, project_id, request_id, correlation_id, task_type,
                    delay_seconds, outcome, status)
                VALUES (:id,:project,:request,:correlation,'diagnostic',:delay,:outcome,'queued')
                ON CONFLICT (request_id) DO NOTHING RETURNING *"""),
                    dict(
                        id=uuid4(),
                        project=project_id,
                        request=request_id,
                        correlation=correlation_id,
                        delay=delay_seconds,
                        outcome=outcome,
                    ),
                )
                .mappings()
                .first()
            )
            if row is not None:
                event(c, row["id"], None, "queued")
            else:
                row = (
                    c.execute(text("SELECT * FROM runs WHERE request_id=:id"), {"id": request_id})
                    .mappings()
                    .one()
                )
                if (
                    row["project_id"],
                    row["correlation_id"],
                    row["delay_seconds"],
                    row["outcome"],
                ) != (project_id, correlation_id, delay_seconds, outcome):
                    raise IdempotencyConflict()
            return record(row)

    def get(self, run_id: UUID) -> Run:
        with self.engine.connect() as c:
            row = (
                c.execute(text("SELECT * FROM runs WHERE id=:id"), {"id": run_id})
                .mappings()
                .first()
            )
        if row is None:
            raise NotFound()
        return record(row)

    def events(self, run_id: UUID, after: int, limit: int) -> list[RunEvent]:
        self.get(run_id)
        with self.engine.connect() as c:
            rows = (
                c.execute(
                    text("""SELECT * FROM run_events WHERE run_id=:id AND sequence>:after
                ORDER BY sequence LIMIT :limit"""),
                    dict(id=run_id, after=after, limit=limit),
                )
                .mappings()
                .all()
            )
        return [RunEvent(**dict(row)) for row in rows]

    def claim(self) -> Run | None:
        with self.engine.begin() as c:
            row = (
                c.execute(
                    text("""SELECT * FROM runs
                WHERE status='queued' OR (status='running' AND
                    (lease_expires_at <= clock_timestamp()
                     OR attempt_deadline <= clock_timestamp()))
                ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1""")
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if row["status"] == "running":
                event(c, row["id"], row["attempt_id"], "lease_expired")
            if row["attempt_count"] >= MAX_ATTEMPTS:
                c.execute(
                    text("""UPDATE runs SET status='failed',error_code='attempts_exhausted',
                    finished_at=clock_timestamp(),lease_expires_at=NULL WHERE id=:id"""),
                    {"id": row["id"]},
                )
                event(c, row["id"], row["attempt_id"], "attempts_exhausted")
                return None
            updated = (
                c.execute(
                    text("""UPDATE runs SET status='running',attempt_id=:attempt,
                attempt_count=attempt_count+1, started_at=COALESCE(started_at,clock_timestamp()),
                lease_expires_at=clock_timestamp()+:lease*interval '1 second',
                attempt_deadline=clock_timestamp()+:deadline*interval '1 second'
                WHERE id=:id RETURNING *"""),
                    dict(
                        id=row["id"],
                        attempt=uuid4(),
                        lease=LEASE_SECONDS,
                        deadline=MAX_ATTEMPT_SECONDS,
                    ),
                )
                .mappings()
                .one()
            )
            event(c, updated["id"], updated["attempt_id"], "started")
            return record(updated)

    def _owned(self, c: Connection, run_id: UUID, attempt_id: UUID) -> bool:
        # Lock first, then check current server time: a lock waiter cannot use a stale lease.
        c.execute(text("SELECT id FROM runs WHERE id=:id FOR UPDATE"), {"id": run_id})
        return (
            c.execute(
                text("""SELECT id FROM runs WHERE id=:id AND attempt_id=:attempt
            AND status='running' AND lease_expires_at>clock_timestamp()
            AND attempt_deadline>clock_timestamp()"""),
                dict(id=run_id, attempt=attempt_id),
            ).first()
            is not None
        )

    def heartbeat(self, run_id: UUID, attempt_id: UUID) -> bool:
        with self.engine.begin() as c:
            if not self._owned(c, run_id, attempt_id):
                return False
            c.execute(
                text("""UPDATE runs SET lease_expires_at=LEAST(attempt_deadline,
                clock_timestamp()+:lease*interval '1 second') WHERE id=:id"""),
                dict(id=run_id, lease=LEASE_SECONDS),
            )
            return True

    def finish(self, run_id: UUID, attempt_id: UUID, error_code: str | None) -> bool:
        if error_code not in (None, "diagnostic_failed"):
            raise ValueError("Unsupported diagnostic error")
        with self.engine.begin() as c:
            if not self._owned(c, run_id, attempt_id):
                return False
            c.execute(
                text("""UPDATE runs SET status=:status, finished_at=clock_timestamp(),
                lease_expires_at=NULL,error_code=:error,output=CAST(:output AS jsonb)
                WHERE id=:id"""),
                dict(
                    id=run_id,
                    status="failed" if error_code else "completed",
                    error=error_code,
                    output=None
                    if error_code
                    else json.dumps(
                        {"message": "Diagnostic completed; no data analysis or AI call performed."}
                    ),
                ),
            )
            event(c, run_id, attempt_id, error_code or "completed")
            return True
