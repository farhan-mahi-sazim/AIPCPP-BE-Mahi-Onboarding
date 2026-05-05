import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from app.main import app
from app.config.db import get_db_session
from app.config.settings import settings
from unittest.mock import MagicMock

# Use a test database URL
TEST_DATABASE_URL = settings.DATABASE_URL_SYNC.replace(
    settings.DB_NAME, f"{settings.DB_NAME}_test"
).replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

        # Manually drop tables with CASCADE to handle circular dependencies
        await conn.execute(sa.text("DROP TABLE IF EXISTS processing_jobs CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS document_chunks CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS document_versions CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS documents CASCADE;"))
        await conn.execute(sa.text("DROP TABLE IF EXISTS users CASCADE;"))

        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    Session = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_storage(monkeypatch):
    mock = MagicMock()
    mock.upload_file.side_effect = lambda file_content, s3_key, content_type: s3_key
    monkeypatch.setattr("app.modules.content.services.storage_service", mock)
    return mock
