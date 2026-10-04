from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Service is temporarily unavailable.")

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Database readiness check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Service is temporarily unavailable.",
        ) from exc

    return {"status": "ok"}
