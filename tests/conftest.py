from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from pkcs.config import get_settings


def alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", str(Path("migrations")))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    database_url = get_settings().database_url
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL is not available for integration tests: {exc}")
    finally:
        engine.dispose()

    command.upgrade(alembic_config(), "head")
    return database_url


@pytest.fixture()
def db_session(migrated_database_url: str) -> Session:
    engine = create_engine(migrated_database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
        session.rollback()
    engine.dispose()

