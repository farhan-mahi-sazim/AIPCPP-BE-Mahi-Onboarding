import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings
from app.models.user import User
from app.modules.processing.tests.constants import (
    MOCK_USER_ID,
    TEST_EMAIL,
    TEST_FULL_NAME,
)

# Use the same logic as conftest.py to get the test database URL but for sync
_url = sa.engine.url.make_url(settings.database_url_sync)
if not _url.database.endswith("_test"):
    _url = _url.set(database=f"{_url.database}_test")

if _url.port == 5434:
    _url = _url.set(port=5433)
elif _url.port == 5432:
    _url = _url.set(port=5433)

SYNC_TEST_DATABASE_URL = _url.render_as_string(hide_password=False)


def get_sync_db_session():
    engine = create_engine(SYNC_TEST_DATABASE_URL, echo=False)
    session_local = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with session_local() as session:
        yield session
    engine.dispose()


def ensure_user_exists_sync(session: Session):
    """Ensures the mock test user exists in the test database (Sync)."""
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
