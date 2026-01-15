"""Async PostgreSQL engine and request-scoped transaction dependencies."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from iri.core.config import get_settings


def build_engine() -> AsyncEngine:
    """Build a pooled engine; schema creation remains Alembic's responsibility."""

    settings = get_settings()
    return create_async_engine(
        settings.postgres_dsn,
        pool_pre_ping=True,
        pool_recycle=1_800,
    )


engine = build_engine()
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one session and guarantee rollback on request failure."""

    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
