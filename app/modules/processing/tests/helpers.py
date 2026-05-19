from sqlalchemy.orm import Session

from app.models.user import User
from app.modules.processing.tests.constants import (
    MOCK_USER_ID,
    TEST_EMAIL,
    TEST_FULL_NAME,
)


def ensure_user_exists_sync(session: Session):
    user = session.get(User, MOCK_USER_ID)
    if not user:
        user = User(
            id=MOCK_USER_ID,
            email=TEST_EMAIL,
            hashed_password="hashed-password",
            full_name=TEST_FULL_NAME,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
