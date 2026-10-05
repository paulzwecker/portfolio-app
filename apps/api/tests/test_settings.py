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
