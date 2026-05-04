import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import text

from app.config.db import engine
from app.modules.healthcheck.constants import DB_CHECK_TIMEOUT
from app.modules.healthcheck.schema import (
    EHealthStatus,
    TDependencyCheck,
    TLivenessResponse,
)


async def check_postgres() -> TDependencyCheck:
    now = datetime.now(tz=timezone.utc)
    start = time.monotonic()
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return TDependencyCheck(
            status=EHealthStatus.PASS,
            observed_value=latency_ms,
            observed_unit="ms",
            time=now,
        )

    except asyncio.TimeoutError:
        return TDependencyCheck(
            status=EHealthStatus.FAIL,
            time=now,
            output=f"timed out after {DB_CHECK_TIMEOUT}s",
        )
    except Exception as exc:
        return TDependencyCheck(
            status=EHealthStatus.FAIL,
            time=now,
            output=str(exc),
        )


async def check_liveness(
    liveness_checker: Callable[[], Awaitable[TLivenessResponse]],
) -> TDependencyCheck:
    now = datetime.now(tz=timezone.utc)
    start = time.monotonic()

    try:
        async with asyncio.timeout(5.0):
            liveness_response = await liveness_checker()
            if liveness_response.status != EHealthStatus.PASS:
                raise ValueError(
                    f"local liveness check returned status '{liveness_response.status}'"
                )

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return TDependencyCheck(
            status=liveness_response.status,
            observed_value=latency_ms,
            observed_unit="ms",
            time=now,
        )

    except asyncio.TimeoutError:
        return TDependencyCheck(
            status=EHealthStatus.FAIL,
            time=now,
            output="liveness check timed out after 5s",
        )

    except Exception as exc:
        return TDependencyCheck(
            status=EHealthStatus.FAIL,
            time=now,
            output=f"local liveness check failed: {exc}",
        )
