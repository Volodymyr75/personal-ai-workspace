"""Separate process using the same PAW backend and database."""

import logging
import signal
from threading import Event

from sqlalchemy.exc import SQLAlchemyError

from paw.application.execution import execute_diagnostic
from paw.config import Settings
from paw.infrastructure.db.catalog import PostgresCatalog
from paw.infrastructure.db.connection import DatabaseReadiness, make_engine
from paw.infrastructure.db.registry import PostgresRegistry
from paw.infrastructure.db.runs import PostgresRuns
from paw.infrastructure.execution.analysis import execute_analysis
from paw.infrastructure.logging import configure_logging
from paw.infrastructure.storage.local import LocalBlobStore
from paw.infrastructure.storage.source import StoredSource


def main() -> int:
    configure_logging()
    logger = logging.getLogger("paw")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        settings = Settings()
        engine = make_engine(settings)
    except ValueError:
        logger.error("configuration_invalid")
        return 1
    blobs = LocalBlobStore(settings.storage_root)
    source = StoredSource(PostgresCatalog(engine, blobs), blobs)
    repo = PostgresRuns(engine, LocalBlobStore(settings.artifact_root, "bin"))
    initialized = False
    try:
        while not stop.is_set():
            try:
                if not initialized:
                    if not DatabaseReadiness(engine).is_ready():
                        stop.wait(2)
                        continue
                    repo.reconcile_artifacts()
                    PostgresRegistry(engine).register_worker()
                    initialized = True
                    logger.info("worker_initialized")
                run = repo.claim()
                if run is None:
                    stop.wait(1)
                elif run.task_type == "csv_analysis":
                    execute_analysis(repo, source, run, stop)
                else:
                    execute_diagnostic(repo, run, stop)
            except (SQLAlchemyError, OSError):
                # Unknown COMMIT outcomes are resolved by durable state and leases.
                logger.warning("worker_storage_unavailable")
                stop.wait(2)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
