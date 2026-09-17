import pytest
from sqlalchemy import Engine

from app.config import settings
from app.db import get_engine


@pytest.fixture(scope="session")
def engine() -> Engine:
    return get_engine()


@pytest.mark.integration
def test_local_database_is_reachable(engine):
    with engine.connect() as conn:
        assert conn.execute(__import__("sqlalchemy").text("SELECT 1")).scalar() == 1
