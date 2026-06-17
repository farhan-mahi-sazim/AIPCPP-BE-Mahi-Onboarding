import pytest

from app.config.test_db import (
    create_sync_engine,
    create_sync_session_factory,
    get_test_db_url,
    setup_test_tables,
)


@pytest.fixture
def sync_engine():
    engine = create_sync_engine(get_test_db_url(sync=True))
    yield engine
    engine.dispose()


@pytest.fixture
def sync_db_session(sync_engine):
    session_factory = create_sync_session_factory(sync_engine)
    with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def cleanup_tables(sync_engine):
    setup_test_tables(sync_engine)
