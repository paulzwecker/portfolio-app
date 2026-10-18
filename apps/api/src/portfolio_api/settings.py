"""Process environment overrides the repository's optional local .env file."""

import re
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

API_PATH = Path(__file__).resolve().parents[2]
REPOSITORY_PATH = API_PATH.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_PATH / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr | None = None
    app_env: Literal["development", "preview", "production"] = "development"
    api_access_token: SecretStr | None = None
    cloud_ingestion_enabled: bool = False
    sec_user_agent: str | None = None
    fmp_api_key: SecretStr | None = None
    google_sheets_spreadsheet_id: str | None = None
    google_sheets_service_account_file: Path | None = None
    google_sheets_sync_tab: str = "Application Model Sync Inbox"
    google_sheets_poll_seconds: int = 3600
    google_sheets_request_timeout_seconds: int = 20
    recurring_operations_enabled: bool = True
    fmp_consensus_ingestion_enabled: bool = False

    @field_validator("google_sheets_spreadsheet_id")
    @classmethod
    def validate_google_spreadsheet_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{20,}", value):
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID must be a spreadsheet ID, not a URL")
        return value

    @field_validator("google_sheets_sync_tab")
    @classmethod
    def validate_google_sheets_sync_tab(cls, value: str) -> str:
        if not value.strip() or "!" in value or len(value) > 100:
            raise ValueError("GOOGLE_SHEETS_SYNC_TAB must be a visible sheet title")
        return value.strip()

    @field_validator("google_sheets_poll_seconds")
    @classmethod
    def validate_google_sheets_poll_seconds(cls, value: int) -> int:
        if value != 0 and value < 60:
            raise ValueError("GOOGLE_SHEETS_POLL_SECONDS must be 0 or at least 60")
        return value

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

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> "Settings":
        if self.app_env in {"preview", "production"}:
            if self.database_url is None:
                raise ValueError("DATABASE_URL is required for remote deployments")
            database_url = make_url(self.database_url.get_secret_value())
            if database_url.host is None:
                raise ValueError("DATABASE_URL must include a direct PostgreSQL endpoint")
            if "-pooler." in database_url.host:
                raise ValueError("DATABASE_URL must use the direct PostgreSQL endpoint")
            sslmode = database_url.query.get("sslmode")
            if sslmode not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("DATABASE_URL must require TLS with sslmode=require or stronger")
        if self.app_env in {"preview", "production"} and (
            self.api_access_token is None or len(self.api_access_token.get_secret_value()) < 32
        ):
            raise ValueError("API_ACCESS_TOKEN with at least 32 characters is required remotely")
        if self.google_sheets_service_account_file is not None:
            path = self.google_sheets_service_account_file.expanduser().resolve()
            if path.is_relative_to(REPOSITORY_PATH.resolve()):
                raise ValueError(
                    "Keep the Google service-account credential outside the repository"
                )
            self.google_sheets_service_account_file = path
        return self
