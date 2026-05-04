import asyncio
from datetime import datetime, timezone

from pytest import MonkeyPatch

from app.modules.healthcheck import helpers
from app.modules.healthcheck.tests.constants import (
    TEST_UNIT_MS,
    TEST_SELECT_1,
    TEST_DB_DOWN,
    TEST_LIVENESS_FAIL,
    TEST_LIVENESS_TIMEOUT,
)
from app.modules.healthcheck.constants import DB_CHECK_TIMEOUT
from app.modules.healthcheck.helpers import check_liveness, check_postgres
from app.modules.healthcheck.schema import EHealthStatus, TLivenessResponse


class _FakeConnection:
    def __init__(self) -> None:
        self.executed_statement: str | None = None

    async def execute(self, statement: object) -> None:
        self.executed_statement = str(statement)


class _FakeConnectContext:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn: _FakeConnection = conn

    async def __aenter__(self) -> _FakeConnection:
        return self.conn

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn: _FakeConnection = conn

    def connect(self) -> _FakeConnectContext:
        return _FakeConnectContext(self.conn)


class _TimeoutOnConnectContext:
    async def __aenter__(self) -> _FakeConnection:
        raise asyncio.TimeoutError

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _ErrorOnConnectContext:
    def __init__(self, error: Exception) -> None:
        self.error: Exception = error

    async def __aenter__(self) -> _FakeConnection:
        raise self.error

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _TimeoutEngine:
    def connect(self) -> _TimeoutOnConnectContext:
        return _TimeoutOnConnectContext()


class _ErrorEngine:
    def __init__(self, error: Exception) -> None:
        self.error: Exception = error

    def connect(self) -> _ErrorOnConnectContext:
        return _ErrorOnConnectContext(self.error)


async def test_check_postgres_passes_and_returns_latency(
    monkeypatch: MonkeyPatch,
) -> None:
    conn = _FakeConnection()
    fake_engine = _FakeEngine(conn)
    monkeypatch.setattr(helpers, "engine", fake_engine)

    result = await check_postgres()

    assert result.status == EHealthStatus.PASS
    assert result.observed_unit == TEST_UNIT_MS
    assert result.observed_value is not None
    assert result.observed_value >= 0
    assert conn.executed_statement == TEST_SELECT_1


async def test_check_postgres_fails_on_timeout(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(helpers, "engine", _TimeoutEngine())

    result = await check_postgres()

    assert result.status == EHealthStatus.FAIL
    assert result.output == f"timed out after {DB_CHECK_TIMEOUT}s"


async def test_check_postgres_fails_on_exception(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(helpers, "engine", _ErrorEngine(RuntimeError(TEST_DB_DOWN)))

    result = await check_postgres()

    assert result.status == EHealthStatus.FAIL
    assert result.output == TEST_DB_DOWN


async def test_check_liveness_passes_with_local_checker() -> None:
    async def fake_liveness() -> TLivenessResponse:
        return TLivenessResponse(
            status=EHealthStatus.PASS,
            timestamp=datetime.now(tz=timezone.utc),
        )

    result = await check_liveness(fake_liveness)

    assert result.status == EHealthStatus.PASS
    assert result.observed_unit == TEST_UNIT_MS
    assert result.observed_value is not None


async def test_check_liveness_fails_with_non_pass_status() -> None:
    async def fake_liveness() -> TLivenessResponse:
        return TLivenessResponse(
            status=EHealthStatus.FAIL,
            timestamp=datetime.now(tz=timezone.utc),
        )

    result = await check_liveness(fake_liveness)

    assert result.status == EHealthStatus.FAIL
    assert TEST_LIVENESS_FAIL in (result.output or "")


async def test_check_liveness_times_out() -> None:
    async def slow_liveness() -> TLivenessResponse:
        await asyncio.sleep(6)
        return TLivenessResponse(
            status=EHealthStatus.PASS,
            timestamp=datetime.now(tz=timezone.utc),
        )

    result = await check_liveness(slow_liveness)

    assert result.status == EHealthStatus.FAIL
    assert result.output == TEST_LIVENESS_TIMEOUT
