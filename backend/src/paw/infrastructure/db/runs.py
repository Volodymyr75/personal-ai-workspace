import json
import logging
from dataclasses import asdict
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping

from paw.domain.analysis import ANALYSIS_ERRORS, MAX_ARTIFACT_BYTES, AnalysisSpec, Artifact, Bundle
from paw.domain.files import BlobStore, NotFound
from paw.domain.runs import (
    LEASE_SECONDS,
    MAX_ATTEMPT_SECONDS,
    MAX_ATTEMPTS,
    IdempotencyConflict,
    Run,
    RunEvent,
)


class PublicationExpired(Exception):
    pass


def record(row: RowMapping) -> Run:
    values = dict(row)
    raw = values.pop("analysis_json")
    values["analysis"] = AnalysisSpec.from_json(raw) if raw is not None else None
    return Run(**values)


def event(c: Connection, run_id: UUID, attempt_id: UUID | None, kind: str) -> None:
    c.execute(
        text("""INSERT INTO run_events (id, run_id, attempt_id, event_type)
        VALUES (:id, :run, :attempt, :kind)"""),
        dict(id=uuid4(), run=run_id, attempt=attempt_id, kind=kind),
    )


class PostgresRuns:
    def __init__(self, engine: Engine, artifacts: BlobStore | None = None):
        self.engine = engine
        self.artifacts = artifacts

    def create(
        self,
        project_id: UUID,
        request_id: UUID,
        correlation_id: UUID | None,
        delay_seconds: int,
        outcome: str,
        file_id: UUID | None = None,
        analysis: AnalysisSpec | None = None,
    ) -> Run:
        if (file_id is None) != (analysis is None):
            raise ValueError("File and analysis must be provided together")
        raw = asdict(analysis) if analysis is not None else None
        normalized = json.loads(json.dumps(raw))
        with self.engine.begin() as c:
            if (
                file_id is not None
                and not c.execute(
                    text("SELECT id FROM files WHERE id=:file AND project_id=:project"),
                    dict(file=file_id, project=project_id),
                ).first()
            ):
                raise NotFound()
            if not c.execute(
                text("SELECT id FROM projects WHERE id=:id"), {"id": project_id}
            ).first():
                raise NotFound()
            row = (
                c.execute(
                    text("""INSERT INTO runs
                (id, project_id, request_id, correlation_id, task_type,
                    delay_seconds, outcome, status, file_id, analysis_json)
                VALUES (:id,:project,:request,:correlation,:task,:delay,:outcome,'queued',
                    :file,CAST(:analysis AS jsonb))
                ON CONFLICT (request_id) DO NOTHING RETURNING *"""),
                    dict(
                        id=uuid4(),
                        project=project_id,
                        request=request_id,
                        correlation=correlation_id,
                        delay=delay_seconds,
                        outcome=outcome,
                        task="csv_analysis" if analysis else "diagnostic",
                        file=file_id,
                        analysis=None if raw is None else json.dumps(raw),
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
                    row["file_id"],
                    row["analysis_json"],
                ) != (project_id, correlation_id, delay_seconds, outcome, file_id, normalized):
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
        if error_code not in (None, "diagnostic_failed") and error_code not in ANALYSIS_ERRORS:
            raise ValueError("Unsupported diagnostic error")
        with self.engine.begin() as c:
            if not self._owned(c, run_id, attempt_id):
                return False
            task = c.execute(
                text("SELECT task_type FROM runs WHERE id=:id"), {"id": run_id}
            ).scalar_one()
            if error_code is None and task != "diagnostic":
                raise ValueError("Analysis requires artifact publication")
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
            event(
                c,
                run_id,
                attempt_id,
                "analysis_failed" if error_code in ANALYSIS_ERRORS else error_code or "completed",
            )
            return True

    def _reconcile_artifacts(self, c: Connection) -> None:
        if self.artifacts is None:
            return
        c.execute(text("SELECT pg_advisory_xact_lock(72841003)"))
        referenced = set(c.execute(text("SELECT id FROM artifacts")).scalars())
        for identity in self.artifacts.ids() - referenced:
            self.artifacts.delete(identity)
        self.artifacts.clear_temporary()

    def reconcile_artifacts(self) -> None:
        with self.engine.begin() as c:
            self._reconcile_artifacts(c)

    def publish(self, run_id: UUID, attempt_id: UUID, bundle: Bundle) -> bool:
        if self.artifacts is None:
            raise OSError("Artifact store unavailable")
        if max(len(bundle.report), len(bundle.chart)) > MAX_ARTIFACT_BYTES:
            raise ValueError("Artifact too large")
        try:
            with self.engine.begin() as c:
                if not self._owned(c, run_id, attempt_id):
                    return False
                task = c.execute(
                    text("SELECT task_type FROM runs WHERE id=:id"), {"id": run_id}
                ).scalar_one()
                if task != "csv_analysis":
                    raise ValueError("Only analysis publishes artifacts")
                self._reconcile_artifacts(c)
                # Recheck after waiting for the shared artifact lock.
                if not self._owned(c, run_id, attempt_id):
                    return False
                output = {"message": "Deterministic analysis completed; no AI call performed."}
                for kind, mime, data in (
                    ("report", "application/json", bundle.report),
                    ("chart", "image/png", bundle.chart),
                ):
                    identity = uuid4()
                    self.artifacts.put(identity, data)
                    c.execute(
                        text("""INSERT INTO artifacts
                        (id,run_id,attempt_id,kind,mime_type,size_bytes,sha256)
                        VALUES (:id,:run,:attempt,:kind,:mime,:size,:sha)"""),
                        dict(
                            id=identity,
                            run=run_id,
                            attempt=attempt_id,
                            kind=kind,
                            mime=mime,
                            size=len(data),
                            sha=sha256(data).hexdigest(),
                        ),
                    )
                    output[kind + "_artifact_id"] = str(identity)
                if not self._owned(c, run_id, attempt_id):
                    raise PublicationExpired()
                c.execute(
                    text("""UPDATE runs SET status='completed',finished_at=clock_timestamp(),
                    lease_expires_at=NULL,output=CAST(:output AS jsonb) WHERE id=:id"""),
                    dict(id=run_id, output=json.dumps(output)),
                )
                event(c, run_id, attempt_id, "completed")
                return True
        except Exception as exc:
            try:
                self.reconcile_artifacts()
            except Exception:
                logging.getLogger("paw").warning("artifact_cleanup_deferred")
            if isinstance(exc, PublicationExpired):
                return False
            raise

    def artifact(self, identity: UUID) -> tuple[Artifact, bytes]:
        with self.engine.connect() as c:
            row = (
                c.execute(
                    text("""SELECT artifacts.* FROM artifacts JOIN runs ON runs.id=run_id
                WHERE artifacts.id=:id AND runs.status='completed'
                AND artifacts.attempt_id=runs.attempt_id"""),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise NotFound()
        if self.artifacts is None:
            raise OSError("Artifact store unavailable")
        artifact = Artifact(**dict(row))
        data = self.artifacts.read(identity, MAX_ARTIFACT_BYTES)
        if len(data) != artifact.size_bytes or sha256(data).hexdigest() != artifact.sha256:
            raise OSError("Artifact integrity mismatch")
        return artifact, data
