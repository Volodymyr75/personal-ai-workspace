"""Separate process using the same PAW backend and database."""

import logging
import signal
from threading import Event

from sqlalchemy.exc import SQLAlchemyError

from paw.application.execution import execute_diagnostic
from paw.config import Settings
from paw.infrastructure.db.connection import DatabaseReadiness, make_engine
from paw.infrastructure.db.registry import PostgresRegistry
from paw.infrastructure.db.runs import PostgresRuns
from paw.infrastructure.logging import configure_logging


def main() -> int:
    configure_logging()
    logger = logging.getLogger("paw")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        engine = make_engine(Settings())
    except ValueError:
        logger.error("configuration_invalid")
        return 1
    repo = PostgresRuns(engine)
    initialized = False
    try:
        while not stop.is_set():
            try:
                if not initialized:
                    if not DatabaseReadiness(engine).is_ready():
                        stop.wait(2)
                        continue
                    PostgresRegistry(engine).register_worker()
                    initialized = True
                    logger.info("worker_initialized")
                run = repo.claim()
                if run is None:
                    stop.wait(1)
                else:
                    execute_diagnostic(repo, run, stop)
            except SQLAlchemyError:
                # Unknown COMMIT outcomes are resolved by durable state and leases.
                logger.warning("worker_database_unavailable")
                stop.wait(2)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
