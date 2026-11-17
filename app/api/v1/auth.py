import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.core.security import (
    DUMMY_HASH,
    current_session,
    current_user,
    digest,
    hasher,
    random_token,
    require_csrf,
    set_cookie,
    verify_password,
)
from app.db.session import get_db
from app.models.entities import AuthAttempt, LoginSession, User
from app.schemas.contracts import AuthOut, Credentials, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def limit_auth(request: Request, email: str, db: AsyncSession, settings: Settings) -> None:
    window = int(time.time()) // 900
    scopes = sorted(
        [
            digest("ip:" + (request.client.host if request.client else "unknown")),
            digest("email:" + email),
        ]
    )
    limited = False
    for scope in scopes:
        statement = insert(AuthAttempt).values(scope=scope, window=window, count=1)
        count = await db.scalar(
            statement.on_conflict_do_update(
                index_elements=["scope", "window"], set_={"count": AuthAttempt.count + 1}
            ).returning(AuthAttempt.count)
        )
        limited = limited or bool(count and count > settings.auth_limit)
    await db.execute(delete(AuthAttempt).where(AuthAttempt.window < window - 1))
    await db.commit()
    if limited:
        raise APIError(429, "auth_rate_limited", "嘗試次數過多，請稍後再試。")


async def establish_session(
    request: Request, response: Response, user: User, db: AsyncSession, settings: Settings
) -> AuthOut:
    old = request.cookies.get(settings.session_cookie)
    if old:
        await db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old)))
    await db.execute(delete(LoginSession).where(LoginSession.expires_at <= datetime.now(UTC)))
    token, csrf = random_token(), random_token()
    max_age = settings.session_days * 86400
    db.add(
        LoginSession(
            token_hash=digest(token),
            user_id=user.id,
            csrf_hash=digest(csrf),
            expires_at=datetime.now(UTC) + timedelta(seconds=max_age),
        )
    )
    await db.commit()
    set_cookie(response, settings.session_cookie, token, settings, max_age)
    set_cookie(response, settings.csrf_cookie, csrf, settings, max_age)
    return AuthOut(user=UserOut.model_validate(user), csrf_token=csrf)


@router.get("/csrf")
async def csrf(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    cookie = request.cookies.get(settings.csrf_cookie, "")
    token = request.cookies.get(settings.session_cookie, "")
    session = await db.get(LoginSession, digest(token)) if token else None
    if len(cookie) < 32 or (session and session.csrf_hash != digest(cookie)):
        cookie = random_token()
        if session:
            session.csrf_hash = digest(cookie)
            await db.commit()
    set_cookie(response, settings.csrf_cookie, cookie, settings, settings.session_days * 86400)
    return {"csrf_token": cookie}


@router.post(
    "/register", response_model=AuthOut, status_code=201, dependencies=[Depends(require_csrf)]
)
async def register(
    data: Credentials,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthOut:
    await limit_auth(request, str(data.email), db, settings)
    encoded = await run_in_threadpool(hasher.hash, data.password.get_secret_value())
    user = User(email=str(data.email), password_hash=encoded)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise APIError(409, "email_exists", "此信箱已被使用，請登入。") from None
    return await establish_session(request, response, user, db, settings)


@router.post("/login", response_model=AuthOut, dependencies=[Depends(require_csrf)])
async def login(
    data: Credentials,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthOut:
    await limit_auth(request, str(data.email), db, settings)
    user = await db.scalar(select(User).where(User.email == str(data.email)))
    encoded = user.password_hash if user else DUMMY_HASH
    valid = await run_in_threadpool(verify_password, encoded, data.password.get_secret_value())
    if not user or not valid:
        raise APIError(401, "invalid_credentials", "信箱或密碼不正確。")
    return await establish_session(request, response, user, db, settings)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: LoginSession = Depends(current_session),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    await db.delete(session)
    await db.commit()
    for name in [settings.session_cookie, settings.csrf_cookie]:
        response.delete_cookie(
            name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
        )
