import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import Session
from app.models.entities import LoginSession, User
from tests.conftest import login


def event(entry="word-0001", **changes):
    return {
        "event_id": str(uuid.uuid4()),
        "entry_id": entry,
        "kind": "quiz",
        "answer": entry,
        **changes,
    }


async def test_health_catalog_and_request_ids(client):
    assert (await client.get("/api/v1/health/live")).json() == {"status": "ok"}
    ready = await client.get("/api/v1/health/ready", headers={"X-Request-ID": "smoke-123"})
    assert ready.status_code == 200
    assert ready.headers["x-request-id"] == "smoke-123"
    words = (await client.get("/api/v1/catalog/vocabulary")).json()["entries"]
    questions = (await client.get("/api/v1/catalog/listening")).json()["entries"]
    assert len(words) == 1000 and len(questions) == 30
    assert words[0]["id"] == "word-0001"
    assert len({row["id"] for row in words + questions}) == 1030
    missing = await client.get("/api/v1/no-such-route")
    assert missing.status_code == 404 and missing.json()["request_id"]


async def test_csrf_blocks_cross_origin_missing_and_prelogin_attacks(client):
    data = {"email": "test@example.com", "password": "a-long-test-password"}
    assert (await client.post("/api/v1/auth/register", json=data)).status_code == 403
    csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    assert (
        await client.post(
            "/api/v1/auth/register",
            json=data,
            headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
        )
    ).status_code == 403
    assert (
        await client.post("/api/v1/auth/register", json=data, headers={"X-CSRF-Token": "wrong"})
    ).status_code == 403


async def test_register_hashes_password_rotates_cookies_and_logout_revokes(client):
    bootstrap = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    result = await login(client, "  Learner@EXAMPLE.com  ")
    assert result["user"]["email"] == "learner@example.com"
    assert result["csrf_token"] != bootstrap
    me = await client.get("/api/v1/auth/me")
    assert me.headers["cache-control"] == "no-store"
    token = client.cookies.get("er_session")
    async with Session() as db:
        user = (await db.scalars(select(User))).one()
        session = (await db.scalars(select(LoginSession))).one()
        assert user.password_hash.startswith("$argon2")
        assert "a-long-test-password" not in user.password_hash
        assert session.token_hash != token and len(session.token_hash) == 64
    cookies = dict(client.cookies)
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    client.cookies.update(cookies)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_login_failure_normalization_duplicate_and_session_expiry(client):
    await login(client)
    client.cookies.clear()
    csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    bad = await client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "incorrect-password"},
    )
    assert bad.status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/register",
            json={"email": "LEARNER@example.com", "password": "a-long-test-password"},
        )
    ).status_code == 409
    good = await client.post(
        "/api/v1/auth/login",
        json={"email": "LEARNER@example.com", "password": "a-long-test-password"},
    )
    assert good.status_code == 200
    async with Session() as db:
        for session in await db.scalars(select(LoginSession)):
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get("/api/v1/progress")).status_code == 401


async def test_private_progress_isolated_and_shared_between_devices(client):
    first = await login(client)
    result = await client.post("/api/v1/progress/events", json=event())
    assert result.status_code == 200 and result.json()["record"]["attempts"] == 1
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(__import__("app.main", fromlist=["app"]).app),
        base_url="http://localhost:3007",
        headers={"Origin": "http://localhost:3007"},
    ) as second:
        await login(second, "other@example.com")
        assert (await second.get("/api/v1/progress")).json()["records"] == []
        assert (
            await second.post(
                "/api/v1/progress/events", json={**event(), "user_id": first["user"]["id"]}
            )
        ).status_code == 422
        csrf = (await second.get("/api/v1/auth/csrf")).json()["csrf_token"]
        response = await second.post(
            "/api/v1/auth/login",
            json={"email": "learner@example.com", "password": "a-long-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        rows = (await second.get("/api/v1/progress")).json()["records"]
        assert len(rows) == 1 and rows[0]["entry_id"] == "word-0001"


async def test_retry_conflict_server_grading_and_card_counters(client):
    await login(client)
    payload = event(answer="word-0002")
    first = await client.post("/api/v1/progress/events", json=payload)
    assert first.json()["correct"] is False and first.json()["record"]["status"] == "review"
    repeated = await client.post("/api/v1/progress/events", json=payload)
    assert repeated.json()["record"]["attempts"] == 1
    assert (
        await client.post("/api/v1/progress/events", json={**payload, "answer": "word-0001"})
    ).status_code == 409
    card = event(kind="card", rating="mastered")
    del card["answer"]
    result = await client.post("/api/v1/progress/events", json=card)
    assert result.json()["record"]["attempts"] == 1
    assert result.json()["record"]["correct"] == 0
    assert result.json()["record"]["status"] == "mastered"
    assert (
        await client.post("/api/v1/progress/events", json=event(entry="listen-001", kind="quiz"))
    ).status_code == 422
    assert (
        await client.post("/api/v1/progress/events", json=event(entry="word-9999"))
    ).status_code == 404
    question = (await client.get("/api/v1/catalog/listening")).json()["entries"][0]
    result = await client.post(
        "/api/v1/progress/events",
        json=event(entry=question["id"], kind="listening", answer=question["answer"]),
    )
    assert result.json()["correct"] is True


async def test_concurrent_retries_and_distinct_events_never_lose_or_double_counts(client):
    await login(client)
    payload = event()
    results = await asyncio.gather(
        *[client.post("/api/v1/progress/events", json=payload) for _ in range(5)]
    )
    assert all(result.status_code == 200 for result in results)
    assert (await client.get("/api/v1/progress")).json()["records"][0]["attempts"] == 1
    results = await asyncio.gather(
        *[client.post("/api/v1/progress/events", json=event()) for _ in range(5)]
    )
    assert all(result.status_code == 200 for result in results)
    assert (await client.get("/api/v1/progress")).json()["records"][0]["attempts"] == 6


async def test_legacy_import_is_idempotent_keeps_status_and_rejects_bad_rows(client):
    await login(client)
    await client.post("/api/v1/progress/events", json=event(answer="word-0002"))
    body = {
        "import_id": str(uuid.uuid4()),
        "records": [
            {"entry_id": "word-0001", "status": "mastered", "attempts": 5, "correct": 4},
            {"entry_id": "listen-001", "status": "review", "attempts": 2, "correct": 1},
        ],
    }
    result = await client.post("/api/v1/progress/import", json=body)
    assert result.status_code == 200, result.text
    word = next(row for row in result.json()["records"] if row["entry_id"] == "word-0001")
    assert word["status"] == "review" and word["attempts"] == 5 and word["correct"] == 4
    repeated = await client.post("/api/v1/progress/import", json=body)
    assert repeated.json()["imported"] == 0
    assert (
        await client.post("/api/v1/progress/import", json={**body, "records": body["records"][:1]})
    ).status_code == 409
    invalid = {
        "import_id": str(uuid.uuid4()),
        "records": [{"entry_id": "word-0001", "status": "review", "attempts": 0, "correct": 2}],
    }
    assert (await client.post("/api/v1/progress/import", json=invalid)).status_code == 422
    invalid["records"][0].update(entry_id="word-9999", correct=0)
    assert (await client.post("/api/v1/progress/import", json=invalid)).status_code == 422


async def test_auth_rate_limit_and_safe_validation_errors(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_limit", 2)
    csrf = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    body = {"email": "nobody@example.com", "password": "incorrect-password"}
    headers = {"X-CSRF-Token": csrf}
    for _ in range(2):
        assert (
            await client.post("/api/v1/auth/login", json=body, headers=headers)
        ).status_code == 401
    assert (await client.post("/api/v1/auth/login", json=body, headers=headers)).status_code == 429
    body["password"] = "short"
    response = await client.post("/api/v1/auth/login", json=body, headers=headers)
    assert response.status_code == 422
    assert "short" not in response.text and "password" in response.text


def test_production_configuration_requires_https_secure_and_postgresql():
    with pytest.raises(ValueError):
        Settings(app_env="production", cookie_secure=False)
    with pytest.raises(ValueError):
        Settings(app_env="production", cookie_secure=True, allowed_origins=["http://example.com"])
    with pytest.raises(ValueError):
        Settings(database_url="sqlite://")
    assert Settings(
        app_env="production", cookie_secure=True, allowed_origins=["https://example.com"]
    ).session_cookie.startswith("__Host-")


async def test_session_bound_csrf_cannot_be_replaced_with_another_cookie(client):
    await login(client)
    forged = "x" * 43
    token = client.cookies.get("er_session")
    response = await client.post(
        "/api/v1/progress/events",
        json=event(),
        headers={"Cookie": f"er_session={token}; er_csrf={forged}", "X-CSRF-Token": forged},
    )
    assert response.status_code == 403
    assert (await client.get("/api/v1/progress")).json()["records"] == []


async def test_production_cookie_flags_and_host_prefix(client, monkeypatch):
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "allowed_origins", ["https://english-reps.example"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://english-reps.example",
        headers={"Origin": "https://english-reps.example"},
    ) as secure:
        csrf = (await secure.get("/api/v1/auth/csrf")).json()["csrf_token"]
        result = await secure.post(
            "/api/v1/auth/register",
            json={"email": "secure@example.com", "password": "a-long-test-password"},
            headers={"X-CSRF-Token": csrf},
        )
        assert result.status_code == 201
        cookies = result.headers.get_list("set-cookie")
        assert len(cookies) == 2
        for cookie in cookies:
            assert "__Host-er_" in cookie and "HttpOnly" in cookie and "Secure" in cookie
            assert "Path=/" in cookie and "SameSite=lax" in cookie and "Domain=" not in cookie
        assert (await secure.get("/api/v1/auth/me")).status_code == 200
