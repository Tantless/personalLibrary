from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pkcs.config import get_settings


def create_db_engine(database_url: str | None = None):
    return create_engine(database_url or get_settings().database_url, future=True)


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_db_engine(database_url), autoflush=False, expire_on_commit=False)


SessionLocal = create_session_factory()


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

