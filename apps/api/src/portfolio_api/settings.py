"""Process environment overrides the repository's optional local .env file."""

import re
from pathlib import Path
from uuid import UUID
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
    database_target_environment: Literal["development", "rehearsal", "production"] | None = None
    database_target_database: str | None = None
    database_local_test_writes_authorized: bool = False
    database_local_writes_authorized: bool = False
    database_rehearsal_writes_authorized: bool = False
    database_production_writes_authorized: bool = False
    neon_api_key: SecretStr | None = None
    neon_project_id: str | None = None
    neon_branch_id: str | None = None
    neon_endpoint_id: str | None = None
    api_access_token: SecretStr | None = None
    model_proposal_agent_token: SecretStr | None = None
    model_proposal_agent_id: str | None = None
    model_proposal_reviewer_token: SecretStr | None = None
    model_proposal_reviewer_id: str | None = None
    observation_proposals_enabled: bool = False
    observation_acceptance_enabled: bool = False
    observation_proposal_agent_token: SecretStr | None = None
    observation_proposal_agent_id: str | None = None
    observation_proposal_reviewer_token: SecretStr | None = None
    observation_proposal_reviewer_id: str | None = None
    data_universe_read_enabled: bool = False
    data_universe_read_token: SecretStr | None = None
    data_universe_read_company_ids: str | None = None
    cloud_ingestion_enabled: bool = False
    sec_user_agent: str | None = None
    fmp_api_key: SecretStr | None = None
    google_sheets_spreadsheet_id: str | None = None
    google_drive_portfolio_workbook_file_id: str | None = None
    google_drive_market_data_workbook_file_id: str | None = None
    google_sheets_service_account_file: Path | None = None
    google_sheets_sync_tab: str = "Application Model Sync Inbox"
    google_sheets_poll_seconds: int = 0
    google_sheets_request_timeout_seconds: int = 20
    recurring_operations_enabled: bool = False
    manual_operations_enabled: bool = False
    workbook_sync_enabled: bool = False
    fmp_consensus_ingestion_enabled: bool = False
    consensus_provider: Literal["fmp_estimates", "eodhd_demo_estimates"] = "fmp_estimates"
    fx_provider: Literal["YAHOO_FINANCE", "ECB_REFERENCE"] = "YAHOO_FINANCE"
    market_data_provider: Literal["YAHOO_FINANCE", "EODHD_DEMO"] = "YAHOO_FINANCE"

    @field_validator("google_sheets_spreadsheet_id")
    @classmethod
    def validate_google_spreadsheet_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{20,}", value):
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID must be a spreadsheet ID, not a URL")
        return value

    @field_validator(
        "google_drive_portfolio_workbook_file_id", "google_drive_market_data_workbook_file_id"
    )
    @classmethod
    def validate_drive_file_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{20,}", value):
            raise ValueError("Google Drive workbook settings must contain a file ID, not a URL")
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

    @field_validator(
        "model_proposal_agent_id",
        "model_proposal_reviewer_id",
        "observation_proposal_agent_id",
        "observation_proposal_reviewer_id",
    )
    @classmethod
    def validate_model_proposal_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 160:
            raise ValueError("Model proposal identities must contain 1 to 160 characters")
        return normalized

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
        if self.consensus_provider == "eodhd_demo_estimates" and (
            self.app_env == "production" or self.database_target_environment == "production"
        ):
            raise ValueError("EODHD consensus demo is isolated-only, not production entitlement")
        if self.market_data_provider == "EODHD_DEMO" and (
            self.app_env == "production" or self.database_target_environment == "production"
        ):
            raise ValueError("EODHD demo coverage is isolated-only, not a production feed approval")
        proposal_roles = (
            (self.model_proposal_agent_token, self.model_proposal_agent_id, "agent"),
            (self.model_proposal_reviewer_token, self.model_proposal_reviewer_id, "reviewer"),
        )
        for token, identity, role in proposal_roles:
            if (token is None) != (identity is None):
                raise ValueError(
                    f"MODEL_PROPOSAL_{role.upper()}_TOKEN and _ID must be configured together"
                )
            if token is not None and len(token.get_secret_value()) < 32:
                raise ValueError(
                    f"MODEL_PROPOSAL_{role.upper()}_TOKEN must contain at least 32 characters"
                )
        if (
            self.model_proposal_agent_token is not None
            and self.model_proposal_reviewer_token is not None
            and self.model_proposal_agent_token.get_secret_value()
            == self.model_proposal_reviewer_token.get_secret_value()
        ):
            raise ValueError("Agent and reviewer proposal tokens must be distinct")
        if (
            self.model_proposal_agent_id is not None
            and self.model_proposal_agent_id == self.model_proposal_reviewer_id
        ):
            raise ValueError("Agent and reviewer proposal identities must be distinct")
        if self.observation_acceptance_enabled and not self.observation_proposals_enabled:
            raise ValueError("Observation acceptance cannot be enabled without proposals")
        observation_roles = (
            (self.observation_proposal_agent_token, self.observation_proposal_agent_id, "AGENT"),
            (
                self.observation_proposal_reviewer_token,
                self.observation_proposal_reviewer_id,
                "REVIEWER",
            ),
        )
        for token, identity, role in observation_roles:
            if (token is None) != (identity is None):
                raise ValueError(f"OBSERVATION_PROPOSAL_{role}_TOKEN and _ID must be paired")
            if token is not None and len(token.get_secret_value()) < 32:
                raise ValueError(f"OBSERVATION_PROPOSAL_{role}_TOKEN must have 32 characters")
        if (
            self.observation_proposal_agent_token is not None
            and self.observation_proposal_reviewer_token is not None
            and self.observation_proposal_agent_token.get_secret_value()
            == self.observation_proposal_reviewer_token.get_secret_value()
        ):
            raise ValueError("Observation agent/reviewer credentials must be distinct")
        if (
            self.observation_proposal_agent_id is not None
            and self.observation_proposal_agent_id == self.observation_proposal_reviewer_id
        ):
            raise ValueError("Observation agent/reviewer identities must be distinct")
        # Narrow, opt-in read token for DATA_UNIVERSE_STEWARD. Reject absent,
        # malformed or ambiguous company scope at configuration time.
        token = self.data_universe_read_token
        ids = self.data_universe_read_company_ids
        if self.data_universe_read_enabled and (token is None or not ids):
            raise ValueError("DATA_UNIVERSE_READ requires a token and a company allowlist")
        if token is not None:
            secret = token.get_secret_value()
            if len(secret) < 32:
                raise ValueError("DATA_UNIVERSE_READ_TOKEN must have at least 32 characters")
            for other in (
                self.api_access_token,
                self.model_proposal_agent_token,
                self.model_proposal_reviewer_token,
                self.observation_proposal_agent_token,
                self.observation_proposal_reviewer_token,
            ):
                if other is not None and secret == other.get_secret_value():
                    raise ValueError("Data Universe read token must be a dedicated credential")
        if ids is not None:
            company_ids = [part.strip() for part in ids.split(",")]
            if not 1 <= len(company_ids) <= 25 or any(not part for part in company_ids):
                raise ValueError("DATA_UNIVERSE_READ_COMPANY_IDS must contain 1–25 UUIDs")
            try:
                parsed = [UUID(part) for part in company_ids]
            except ValueError as error:
                raise ValueError("DATA_UNIVERSE_READ_COMPANY_IDS contains an invalid UUID") from error
            if len(set(parsed)) != len(parsed) or any(
                str(value) != supplied for value, supplied in zip(parsed, company_ids)
            ):
                raise ValueError("DATA_UNIVERSE_READ_COMPANY_IDS must be unique canonical UUIDs")
        if self.app_env in {"preview", "production"}:
            if self.database_url is None:
                raise ValueError("DATABASE_URL is required for remote deployments")
            database_url = make_url(self.database_url.get_secret_value())
            if database_url.host is None:
                raise ValueError("DATABASE_URL must include a direct PostgreSQL endpoint")
            if "-pooler." in database_url.host:
                raise ValueError("DATABASE_URL must use the direct PostgreSQL endpoint")
            sslmode = database_url.query.get("sslmode")
            if sslmode != "verify-full":
                raise ValueError("DATABASE_URL must use sslmode=verify-full for remote deployments")
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
