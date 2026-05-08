import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.db import get_db_session
from app.config.settings import settings
from app.modules.healthcheck.constants import PROCESS_START
from app.modules.healthcheck.helpers import check_liveness, check_postgres
from app.modules.healthcheck.schema import (
    EHealthStatus,
    THealthCheckResponse,
    TLivenessResponse,
)

router = APIRouter(prefix="/healthcheck", tags=["healthcheck"])


@router.get("", response_model=THealthCheckResponse, status_code=200)
async def health_check(
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    db_check = await check_postgres()
    liveness_check = await check_liveness(lambda: liveness(session))

    overall = EHealthStatus.FAIL
    if (
        db_check.status == EHealthStatus.PASS
        and liveness_check.status == EHealthStatus.PASS
    ):
        overall = EHealthStatus.PASS

    status_code = 200 if overall == EHealthStatus.PASS else 503

    body = THealthCheckResponse(
        status=overall,
        version=settings.APP_VERSION,
        description="AI-content processing pipeline",
        timestamp=datetime.now(tz=UTC),
        uptime_seconds=round(time.monotonic() - PROCESS_START, 2),
        environment=settings.ENVIRONMENT,
        checks={"postgres": db_check, "liveness": liveness_check},
        output=(
            None
            if overall == EHealthStatus.PASS
            else "one or more dependencies are unhealthy"
        ),
    )

    return JSONResponse(content=body.model_dump(mode="json"), status_code=status_code)


@router.get("/live", response_model=TLivenessResponse, status_code=200)
async def liveness(
    session: AsyncSession = Depends(get_db_session),
) -> TLivenessResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return TLivenessResponse(
            status=EHealthStatus.FAIL,
            timestamp=datetime.now(tz=UTC),
        )
    return TLivenessResponse(
        status=EHealthStatus.PASS,
        timestamp=datetime.now(tz=UTC),
    )


@router.get("/ready", response_model=THealthCheckResponse, status_code=200)
async def readiness() -> JSONResponse:
    return await health_check()
