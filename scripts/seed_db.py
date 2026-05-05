import asyncio
import uuid
from sqlmodel import select
from app.config.db import AsyncSessionLocal, engine
from app.models.user import User


async def seed():
    print("🌱 Seeding database...")
    DUMMY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == DUMMY_USER_ID))
        user = result.scalar_one_or_none()

        if not user:
            default_user = User(
                id=DUMMY_USER_ID,
                email="dev@example.com",
                hashed_password="not-a-real-password",
                full_name="Default Dev User",
                is_active=True,
            )
            session.add(default_user)
            await session.commit()
            print(f"✅ Created default user: {default_user.email}")
        else:
            print("✨ Default user already exists.")

    await engine.dispose()
    print("🏁 Seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed())
