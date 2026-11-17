import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db.session import get_db
from app.models.entities import LoginSession, User

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash("unused-dummy-password-for-timing")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def set_cookie(response: Response, name: str, value: str, settings: Settings, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def require_csrf(request: Request, settings: Settings = Depends(get_settings)) -> None:
    origin = request.headers.get("origin")
    cookie = request.cookies.get(settings.csrf_cookie, "")
    header = request.headers.get("x-csrf-token", "")
    if (
        origin not in settings.allowed_origins
        or len(cookie) < 32
        or not hmac.compare_digest(cookie, header)
    ):
        raise APIError(403, "csrf_failed", "安全驗證失敗，請重新整理後再試。")


async def current_session(
    request: Request, db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
) -> LoginSession:
    token = request.cookies.get(settings.session_cookie, "")
    session = await db.get(LoginSession, digest(token)) if token else None
    if session is None or session.expires_at <= datetime.now(UTC):
        raise APIError(401, "unauthenticated", "請先登入。")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf(request, settings)
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(session.csrf_hash, digest(csrf)):
            raise APIError(403, "csrf_failed", "登入驗證已更新，請重新整理。")
    return session


async def current_user(
    session: LoginSession = Depends(current_session), db: AsyncSession = Depends(get_db)
) -> User:
    user = await db.get(User, session.user_id)
    if user is None:
        raise APIError(401, "unauthenticated", "請先登入。")
    return user


def random_token() -> str:
    return secrets.token_urlsafe(32)
