import os
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import text

url = os.environ.get("TEST_DATABASE_URL", "")
if not url or "test" not in url.rsplit("/", 1)[-1]:
    raise RuntimeError(
        "Set TEST_DATABASE_URL to a dedicated PostgreSQL database with 'test' in its name"
    )
os.environ["DATABASE_URL"] = url
os.environ["APP_ENV"] = "test"

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE users, sessions, progress, study_events, progress_imports, auth_attempts CASCADE"
            )
        )
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:3007",
        headers={"Origin": "http://localhost:3007"},
    ) as client:
        yield client


async def login(client: httpx.AsyncClient, email: str = "learner@example.com") -> dict[str, str]:
    token = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    result = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-test-password"},
        headers={"X-CSRF-Token": token},
    )
    assert result.status_code == 201, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return result.json()
