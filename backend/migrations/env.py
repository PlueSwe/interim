"""Alembics miljo.

Adressen till databasen kommer ur app.config och inte ur alembic.ini. Da kan
samma kommando koras i en container, pa en VPS och lokalt utan att filen andras,
och det finns ingen risk att en migrering trillar in i fel databas for att tva
filer sa olika saker.

compare_type och compare_server_default ar pa. Utan dem missar autogenerate att
en kolumn bytt typ, och den sortens tysta skillnad mellan modell och databas ar
precis vad migreringar finns for att undvika.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Hall pgvectors egna tabeller utanfor autogenerate."""
    return not (type_ == "table" and name in {"vector", "pg_stat_statements"})


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as anslutning:
        context.configure(
            connection=anslutning,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
