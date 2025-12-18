"""
Alembic migration environment configuration
"""

import sys
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from sqlalchemy.engine import Connection

from alembic import context

# Add shared to path
sys.path.insert(0, '/app/shared')

from models import Base
from config import Config

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata

# Load application config
app_config = Config()


def get_sync_url() -> str:
    """Get sync database URL from config (convert asyncpg to psycopg2)"""
    url = app_config.database_url
    # Replace asyncpg with psycopg2 if needed
    if '+asyncpg' in url:
        url = url.replace('+asyncpg', '')
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    """
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode with sync engine.
    """
    connectable = create_engine(
        get_sync_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
