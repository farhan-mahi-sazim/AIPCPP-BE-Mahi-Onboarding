import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

from app.config.settings import settings


def get_test_db_url(sync: bool = True) -> str:
    _url = sa.engine.url.make_url(settings.database_url_sync)
    if not _url.database.endswith("_test"):
        _url = _url.set(database=f"{_url.database}_test")

    if _url.port == 5434:
        _url = _url.set(port=5433)
    elif _url.port == 5432:
        _url = _url.set(port=5433)

    url_str = _url.render_as_string(hide_password=False)
    if sync:
        return url_str
    return url_str.replace("postgresql+psycopg://", "postgresql+asyncpg://")


def create_sync_engine(url: str):
    return create_engine(url, echo=False)


def create_sync_session_factory(engine):
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def create_sync_session(url: str):
    engine = create_engine(url, echo=False)
    session_local = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    session = session_local()
    yield session
    engine.dispose()


def setup_test_tables(engine):
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS processing_jobs CASCADE"))
        conn.execute(sa.text("DROP TABLE IF EXISTS document_chunks CASCADE"))
        conn.execute(sa.text("DROP TABLE IF EXISTS document_versions CASCADE"))
        conn.execute(sa.text("DROP TABLE IF EXISTS documents CASCADE"))
        conn.execute(sa.text("DROP TABLE IF EXISTS users CASCADE"))
    SQLModel.metadata.create_all(engine)
