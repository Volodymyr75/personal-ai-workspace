from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAW_", extra="ignore")

    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "paw"
    db_user: str = "paw"
    db_password: SecretStr
    storage_root: Path = Path("/data/files")
    artifact_root: Path = Path("/data/artifacts")
    api_url: str = "http://127.0.0.1:8000"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
