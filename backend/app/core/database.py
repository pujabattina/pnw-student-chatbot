from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import AppSettings, get_settings


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def database_lifespan(
    app: FastAPI,
    settings: AppSettings | None = None,
) -> AsyncIterator[None]:
    resolved_settings = settings or get_settings()
    engine = create_async_engine(
        resolved_settings.database_url,
        pool_pre_ping=True,
        future=True,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))

    try:
        yield
    finally:
        await engine.dispose()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    async_session_factory = create_session_factory(settings.database_url)
    async with async_session_factory() as session:
        yield session
