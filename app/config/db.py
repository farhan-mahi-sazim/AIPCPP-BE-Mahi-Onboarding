from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
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


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Initialize database and seed default user for development."""
    from app.models.user import User
    from sqlmodel import select
    import uuid

    DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == DUMMY_USER_ID))
        user = result.scalar_one_or_none()

        if not user:
            default_user = User(
                id=DUMMY_USER_ID,
                email="dev@example.com",
                hashed_password="not-a-real-password",  # No auth yet
                full_name="Default Dev User",
                is_active=True,
            )
            session.add(default_user)
            await session.commit()
