from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

sync_engine = create_engine(
    settings.database_url_sync,
    echo=False,
    future=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Initialize database and seed default user for development."""
    import uuid

    from sqlmodel import select

    from app.models.user import User

    dummy_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == dummy_user_id))
        user = result.scalar_one_or_none()

        if not user:
            default_user = User(
                id=dummy_user_id,
                email="dev@example.com",
                hashed_password="not-a-real-password",  # No auth yet
                full_name="Default Dev User",
                is_active=True,
            )
            session.add(default_user)
            await session.commit()
