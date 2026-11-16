from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from monitor.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _upgrade_schema(connection) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parent / "migrations")
    )
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def init_db() -> None:
    from monitor import models  # noqa: F401

    async with engine.begin() as connection:
        # Serialize simultaneous first startup of bot and userbot.
        await connection.execute(text("SELECT pg_advisory_xact_lock(771923501)"))
        await connection.run_sync(_upgrade_schema)


async def close_db() -> None:
    await engine.dispose()
