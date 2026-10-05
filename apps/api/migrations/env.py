"""Run explicit schema migrations using the same settings as the application."""

from alembic import context
from sqlalchemy.engine import Connection

from portfolio_api.database import Base, create_database_engine
from portfolio_api.domain import models  # noqa: F401 -- register domain metadata
from portfolio_api.settings import Settings

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = Settings()
    if settings.database_url is None:
        raise RuntimeError(
            "Set DATABASE_URL in the environment or repository .env before migrating"
        )
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if isinstance(supplied_connection, Connection):
        migrate_connection(supplied_connection)
        return

    engine = create_database_engine(Settings())
    if engine is None:
        raise RuntimeError(
            "Set DATABASE_URL in the environment or repository .env before migrating"
        )
    try:
        with engine.connect() as connection:
            migrate_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
