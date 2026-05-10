import asyncio
from unittest.mock import MagicMock

import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.common.storage import get_storage_service
from app.config.db import get_db_session
from app.config.settings import settings
from app.main import app

# Use a test database URL safely
_url = sa.engine.url.make_url(settings.database_url_sync)
if not _url.database.endswith("_test"):
    _url = _url.set(database=f"{_url.database}_test")

# If using local dev port 5434, switch to test port 5433
if _url.port == 5434:
    _url = _url.set(port=5433)
elif _url.port == 5432:  # Fallback for standard port
    _url = _url.set(port=5433)

TEST_DATABASE_URL = _url.render_as_string(hide_password=False).replace(
    "postgresql+psycopg://", "postgresql+asyncpg://"
)


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Retry logic for CI stability (waits for Postgres to be ready)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                # Enable pgvector extension
                await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

                # Manually drop tables with CASCADE to handle circular dependencies
                await conn.execute(
                    sa.text("DROP TABLE IF EXISTS processing_jobs CASCADE;")
                )
                await conn.execute(
                    sa.text("DROP TABLE IF EXISTS document_chunks CASCADE;")
                )
                await conn.execute(
                    sa.text("DROP TABLE IF EXISTS document_versions CASCADE;")
                )
                await conn.execute(sa.text("DROP TABLE IF EXISTS documents CASCADE;"))
                await conn.execute(sa.text("DROP TABLE IF EXISTS users CASCADE;"))

                # Also drop enum types to ensure they are recreated with updated members
                await conn.execute(sa.text("DROP TYPE IF EXISTS efiletype CASCADE;"))
                await conn.execute(
                    sa.text("DROP TYPE IF EXISTS eversionsource CASCADE;")
                )
                await conn.execute(sa.text("DROP TYPE IF EXISTS ejobstatus CASCADE;"))
                await conn.execute(
                    sa.text("DROP TYPE IF EXISTS epipelinestage CASCADE;")
                )

                # Create all tables
                await conn.run_sync(SQLModel.metadata.create_all)
            break
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            await asyncio.sleep(2)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    mock_storage = MagicMock()
    mock_storage.upload_file.side_effect = (
        lambda file_obj, s3_key, content_type, max_size=None: s3_key
    )

    # Mock Celery tasks
    import app.modules.content.services as services_module

    original_trigger = services_module.ContentService._trigger_pipeline

    async def mock_trigger(self, doc_id):
        """Skip Celery pipeline in tests"""
        pass

    services_module.ContentService._trigger_pipeline = mock_trigger

    async def override_get_db_session():
        yield db_session

    async def override_get_storage_service():
        yield mock_storage

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_storage_service] = override_get_storage_service

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        ac.mock_storage = mock_storage
        yield ac

    services_module.ContentService._trigger_pipeline = original_trigger
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def mock_celery():
    """Mock Celery tasks for all tests"""
    import app.modules.content.services as services_module

    original_trigger = services_module.ContentService._trigger_pipeline

    async def mock_trigger(self, doc_id):
        """Skip Celery pipeline in tests"""
        pass

    services_module.ContentService._trigger_pipeline = mock_trigger
    yield
    services_module.ContentService._trigger_pipeline = original_trigger
