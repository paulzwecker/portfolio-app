"""Database connectivity and metadata; migrations own schema changes."""

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from portfolio_api.database_write_target import (
    WriteOperationKind,
    install_database_write_target_guard,
)
from portfolio_api.settings import Settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def create_database_engine(
    settings: Settings,
    *,
    write_operation: str = "application_write",
    write_operation_kind: WriteOperationKind = "application",
) -> Engine | None:
    if settings.database_url is None:
        return None
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )
    install_database_write_target_guard(
        engine,
        settings,
        operation=write_operation,
        operation_kind=write_operation_kind,
    )
    return engine
