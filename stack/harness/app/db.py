"""Async SQLAlchemy engine + session factory. Tables are created on startup."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    # Research stack: create_all is sufficient. Switch to Alembic if the
    # schema starts evolving while data must survive.
    from app import models  # noqa: F401  (register mappers)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def db_session() -> AsyncSession:
    return AsyncSessionLocal()
