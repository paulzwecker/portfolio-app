"""Process environment overrides the repository's optional local .env file."""

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

API_PATH = Path(__file__).resolve().parents[2]
REPOSITORY_PATH = API_PATH.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_PATH / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr | None = None
    sec_user_agent: str | None = None
    fmp_api_key: SecretStr | None = None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
            if url.drivername != "postgresql+psycopg" or not url.database:
                raise ValueError
            _ = url.port
        except (ArgumentError, ValueError) as error:
            raise ValueError(
                "DATABASE_URL must be a postgresql+psycopg URL with a database name"
            ) from error
        return value
