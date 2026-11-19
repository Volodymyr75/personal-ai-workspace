import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def engine():
    value = os.environ.get("PAW_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set PAW_TEST_DATABASE_URL for isolated PostgreSQL integration tests")
    url = make_url(value)
    if url.database != "paw_test":
        pytest.fail("Integration tests require a dedicated database named paw_test")
    schema = f"test_{uuid4().hex}"
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    tested = create_engine(
        url,
        hide_parameters=True,
        connect_args={
            "options": f"-c search_path={schema} -c timezone=UTC -c statement_timeout=5000",
        },
    )
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    try:
        with tested.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield tested
    finally:
        tested.dispose()
        # Only the freshly generated schema in the explicitly named test DB is removed.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
