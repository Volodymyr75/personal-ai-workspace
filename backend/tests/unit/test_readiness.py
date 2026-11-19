from unittest.mock import Mock

from sqlalchemy.exc import OperationalError

from paw.config import Settings
from paw.infrastructure.db.connection import DatabaseReadiness


def test_database_errors_are_redacted(caplog):
    engine = Mock()
    engine.connect.side_effect = OperationalError("secret-query", {}, Exception("private-password"))
    assert not DatabaseReadiness(engine).is_ready()
    assert "private-password" not in caplog.text
    assert "secret-query" not in caplog.text
    assert "database_not_ready" in caplog.text


def test_password_is_not_part_of_settings_representation():
    settings = Settings(db_password="private-password")
    assert "private-password" not in repr(settings)
    assert "private-password" not in str(settings.database_url)
