import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.v1 import auth, catalog, mock_exams, progress
from app.core.errors import error_response, http_error, validation_error
from app.db.session import engine
from app.services.catalog import get_catalog

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    get_catalog()
    yield
    await engine.dispose()


app = FastAPI(title="English Reps API", version="1.0.0", lifespan=lifespan)
app.add_exception_handler(HTTPException, http_error)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error)  # type: ignore[arg-type]


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    supplied = request.headers.get("x-request-id", "")
    request.state.request_id = (
        supplied if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", supplied) else str(uuid.uuid4())
    )
    response: Response
    try:
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 262144:
            response = error_response(request, 413, "body_too_large", "請求資料過大。")
        else:
            response = await call_next(request)
    except SQLAlchemyError:
        response = error_response(
            request, 503, "database_unavailable", "資料服務暫時無法使用，請稍後重試。"
        )
    except Exception:
        logger.error("Unhandled API error; request_id=%s", request.state.request_id)
        response = error_response(request, 500, "internal_error", "服務暫時無法使用。")
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    if (
        "/auth/" in request.url.path
        or "/progress" in request.url.path
        or "/mock-exams" in request.url.path
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT id FROM users LIMIT 1"))
    if get_catalog().total_count == 0:
        raise RuntimeError("Catalog is empty")
    return {"status": "ready"}


for router in [auth.router, catalog.router, progress.router, mock_exams.router]:
    app.include_router(router, prefix="/api/v1")
