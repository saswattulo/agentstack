import pytest

from agentstack.config import Settings


@pytest.mark.unit
def test_sqlalchemy_url_built_from_components():
    s = Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert s.sqlalchemy_url == "postgresql+asyncpg://u:p@h:1234/d"


@pytest.mark.unit
def test_sync_url_swaps_driver():
    s = Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert s.sync_sqlalchemy_url == "postgresql+psycopg://u:p@h:1234/d"


@pytest.mark.unit
def test_explicit_database_url_wins():
    s = Settings(database_url="postgresql+asyncpg://x:y@z/db")
    assert s.sqlalchemy_url == "postgresql+asyncpg://x:y@z/db"


@pytest.mark.unit
def test_celery_uses_different_redis_dbs():
    s = Settings(redis_host="rhost", redis_port=6379)
    assert s.celery_broker.endswith("/1")
    assert s.celery_backend.endswith("/2")
