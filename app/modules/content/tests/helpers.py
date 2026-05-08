from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user import User
from app.modules.content.tests.constants import DUMMY_USER_ID


async def ensure_user_exists(db_session: AsyncSession):
    """Ensures the dummy test user exists in the test database."""
    result = await db_session.execute(select(User).where(User.id == DUMMY_USER_ID))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=DUMMY_USER_ID,
            email="test@example.com",
            hashed_password="hashed-password",
            full_name="Test User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
    return user
