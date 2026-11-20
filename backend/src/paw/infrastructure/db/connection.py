import logging

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from paw.config import Settings

SCHEMA_REVISION = "0004_analysis_artifacts"
logger = logging.getLogger("paw")


def make_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC -c statement_timeout=5000"},
    )


class DatabaseReadiness:
    def __init__(self, engine: Engine):
        self.engine = engine

    def is_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                # A migrated DB is required: connectivity alone is not application readiness.
                connection.execute(text("SELECT key FROM service_nodes LIMIT 0"))
                connection.execute(text("SELECT key FROM service_edges LIMIT 0"))
                connection.execute(text("SELECT id FROM system_events LIMIT 0"))
                connection.execute(text("SELECT id FROM projects LIMIT 0"))
                connection.execute(text("SELECT id FROM files LIMIT 0"))
                connection.execute(text("SELECT id FROM runs LIMIT 0"))
                connection.execute(text("SELECT id FROM run_events LIMIT 0"))
                connection.execute(text("SELECT id FROM artifacts LIMIT 0"))
                return revision == SCHEMA_REVISION
        except SQLAlchemyError:
            logger.warning("database_not_ready")
            return False
