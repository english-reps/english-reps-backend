import pytest

from app.core.config import Settings


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_provider_database_urls_keep_encoded_credentials_and_use_async_driver(scheme):
    settings = Settings(database_url=f"{scheme}://user:p%40ss%3Aword@host/db?sslmode=require")
    assert settings.database_url == "postgresql+asyncpg://user:p%40ss%3Aword@host/db?ssl=require"


def test_provider_database_url_does_not_weaken_production_validation():
    with pytest.raises(ValueError):
        Settings(
            database_url="postgresql://user:pw@host/db", app_env="production", cookie_secure=False
        )
