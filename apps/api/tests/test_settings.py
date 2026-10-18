import re
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from portfolio_api.database import create_database_engine
from portfolio_api.settings import Settings


def test_database_url_is_not_represented_in_settings() -> None:
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:private-password@127.0.0.1/test"),
    )
    assert "private-password" not in repr(settings)


@pytest.mark.parametrize("url", ["sqlite://", "postgresql://user:secret@host/db", "invalid-secret"])
def test_only_psycopg_postgresql_urls_are_supported(url: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(database_url=SecretStr(url))
    assert "secret" not in str(error.value)


def test_missing_configuration_does_not_create_engine() -> None:
    assert create_database_engine(Settings(database_url=None)) is None


def test_invalid_google_spreadsheet_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must be a spreadsheet ID"):
        Settings(
            _env_file=None,
            google_sheets_spreadsheet_id="https://docs.google.com/spreadsheets/d/fictional/edit",
        )


def test_empty_google_sheets_environment_disables_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    monkeypatch.setenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "")

    settings = Settings(_env_file=None)

    assert settings.google_sheets_spreadsheet_id is None
    assert settings.google_sheets_service_account_file is None


def test_empty_google_sheets_values_in_dotenv_disable_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "GOOGLE_SHEETS_SPREADSHEET_ID=\nGOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=\n",
        encoding="utf-8",
    )

    class DotenvSettings(Settings):
        model_config = SettingsConfigDict(env_file=dotenv_path)

    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", raising=False)
    settings = DotenvSettings()

    assert settings.google_sheets_spreadsheet_id is None
    assert settings.google_sheets_service_account_file is None


def test_ci_workflow_leaves_google_sheets_unconfigured() -> None:
    workflow = Path(__file__).resolve().parents[3] / ".github/workflows/ci.yml"
    contents = workflow.read_text(encoding="utf-8")
    example = workflow.parents[2] / ".env.example"
    example_contents = example.read_text(encoding="utf-8")

    assert re.search(
        r"(?m)^env:\n  APP_ENV: development\n"
        r'  GOOGLE_SHEETS_SPREADSHEET_ID: ""\n'
        r'  GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE: ""$',
        contents,
    )
    assert re.search(r"(?m)^GOOGLE_SHEETS_SPREADSHEET_ID=$", example_contents)
    assert re.search(r"(?m)^GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=$", example_contents)
    assert "${{ secrets." not in contents


def test_process_environment_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "DATABASE_URL=postgresql+psycopg://file-user@127.0.0.1/file_database\n"
        "UNRELATED_FRONTEND_SETTING=ignored\n",
        encoding="utf-8",
    )

    class FileSettings(Settings):
        model_config = SettingsConfigDict(env_file=dotenv_path)

    process_url = "postgresql+psycopg://process-user@127.0.0.1/process_database"
    monkeypatch.setenv("DATABASE_URL", process_url)
    assert FileSettings().database_url == SecretStr(process_url)


def test_dotenv_load_does_not_depend_on_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_url = "postgresql+psycopg://file-user@127.0.0.1/file_database"
    dotenv_path.write_text(f"DATABASE_URL={dotenv_url}\n", encoding="utf-8")
    nested_path = tmp_path / "nested"
    nested_path.mkdir()

    class FileSettings(Settings):
        model_config = SettingsConfigDict(env_file=dotenv_path)

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(nested_path)
    assert FileSettings().database_url == SecretStr(dotenv_url)
