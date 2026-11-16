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
    # In Docker, the project files live in /app while the installed Python
    # package lives in site-packages. Resolve alembic.ini from the app working
    # directory first instead of deriving it from the installed package path.
    candidates = (
        Path.cwd() / "alembic.ini",
        Path(__file__).resolve().parents[2] / "alembic.ini",
    )
    alembic_ini = next((path.resolve() for path in candidates if path.is_file()), None)
    if alembic_ini is None:
        searched = ", ".join(str(path.resolve()) for path in candidates)
        raise FileNotFoundError(
            f"Could not find alembic.ini. Checked: {searched}. "
            "Make sure the application is started with /app as its working directory."
        )

    config = Config(str(alembic_ini))
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
