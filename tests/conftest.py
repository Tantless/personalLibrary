import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from pkcs.config import get_settings

TEST_DATABASE_ENV = "PKCS_TEST_DATABASE_URL"
RESERVED_DATABASE_NAMES = {"postgres", "template0", "template1"}


def alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", str(Path("migrations")))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    database_url = _prepare_test_database()
    os.environ["PKCS_DATABASE_URL"] = database_url
    get_settings.cache_clear()

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


def _prepare_test_database() -> str:
    settings = get_settings()
    base_url = make_url(settings.database_url)
    configured_test_url = (
        settings.test_database_url
        or os.environ.get(TEST_DATABASE_ENV)
        or _default_test_database_url(base_url)
    )
    test_url = make_url(configured_test_url)
    _validate_test_database_url(base_url, test_url)

    maintenance_url = _maintenance_url(test_url)
    engine = create_engine(maintenance_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(f"drop database if exists {_quoted_identifier(test_url.database)} with (force)")
            )
            connection.execute(text(f"create database {_quoted_identifier(test_url.database)}"))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL is not available for integration tests: {exc}")
    finally:
        engine.dispose()
    return test_url.render_as_string(hide_password=False)


def _validate_test_database_url(base_url: URL, test_url: URL) -> None:
    test_database_name = test_url.database
    if base_url.database == test_database_name:
        pytest.fail(
            "pytest database isolation refused to use the application database; "
            f"set {TEST_DATABASE_ENV} to a separate test database"
        )
    if not test_database_name:
        pytest.fail(f"{TEST_DATABASE_ENV} must include a database name")
    if test_database_name in RESERVED_DATABASE_NAMES or not test_database_name.endswith("_test"):
        pytest.fail(f"{TEST_DATABASE_ENV} must point to a dedicated database whose name ends with '_test'")


def _default_test_database_url(base_url: URL) -> str:
    database_name = base_url.database or "pkcs"
    return base_url.set(database=f"{database_name}_test").render_as_string(hide_password=False)


def _maintenance_url(database_url: URL) -> URL:
    return database_url.set(database="postgres")


def _quoted_identifier(value: str | None) -> str:
    if not value:
        raise ValueError("database name must not be empty")
    return '"' + value.replace('"', '""') + '"'
