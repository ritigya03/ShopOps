from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.config import settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(settings.local_database_url)
