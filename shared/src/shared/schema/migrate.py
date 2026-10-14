"""Create roles (as superuser) and apply Alembic migrations (as app_owner)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config.migrate import MigrateSettings
from shared.schema.roles import RolePasswords, role_statements

ALEMBIC_DIR = Path(__file__).parent / "alembic"


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("version_locations", str(ALEMBIC_DIR / "versions"))
    config.set_main_option("path_separator", "os")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def upgrade(owner_url: str) -> None:
    command.upgrade(alembic_config(owner_url), "heads")


def downgrade(owner_url: str) -> None:
    command.downgrade(alembic_config(owner_url), "base")


async def ensure_roles(admin_url: str, database: str, passwords: RolePasswords) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            for statement in role_statements(database, passwords):
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


def main() -> None:
    settings = MigrateSettings()
    asyncio.run(
        ensure_roles(
            settings.url(settings.postgres_user, settings.postgres_password),
            settings.postgres_db,
            settings.passwords(),
        )
    )
    upgrade(settings.url("app_owner", settings.app_owner_password))
    print("migrations applied")  # noqa: T201
