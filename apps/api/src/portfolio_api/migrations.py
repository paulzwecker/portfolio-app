"""Shared Alembic configuration without putting credentials in configuration files."""

from alembic.config import Config
from alembic.script import ScriptDirectory

from portfolio_api.settings import API_PATH


def alembic_config() -> Config:
    return Config(str(API_PATH / "alembic.ini"))


def expected_heads() -> set[str]:
    return set(ScriptDirectory.from_config(alembic_config()).get_heads())
