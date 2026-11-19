import argparse
import logging

from sqlalchemy.exc import SQLAlchemyError

from paw.application.bootstrap import BootstrapUnavailable, bootstrap
from paw.config import Settings
from paw.infrastructure.api_probe import HttpApiProbe
from paw.infrastructure.db.connection import DatabaseReadiness, make_engine
from paw.infrastructure.db.registry import PostgresRegistry
from paw.infrastructure.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="PAW local administration")
    parser.add_argument("command", choices=["bootstrap"])
    parser.parse_args()
    configure_logging()
    logger = logging.getLogger("paw")
    try:
        settings = Settings()
    except ValueError:
        logger.error("configuration_invalid")
        return 1
    engine = make_engine(settings)
    try:
        added = bootstrap(
            HttpApiProbe(settings.api_url), DatabaseReadiness(engine), PostgresRegistry(engine)
        )
        logger.info("bootstrap_registered" if added else "bootstrap_unchanged")
        return 0
    except (BootstrapUnavailable, SQLAlchemyError, ValueError):
        logger.error("bootstrap_failed")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
