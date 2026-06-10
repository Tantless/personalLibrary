from sqlalchemy import text
from sqlalchemy.engine import make_url


def test_pytest_uses_dedicated_test_database(db_session, migrated_database_url) -> None:
    database_name = make_url(migrated_database_url).database

    assert database_name is not None
    assert database_name.endswith("_test")
    assert db_session.scalar(text("select current_database()")) == database_name
