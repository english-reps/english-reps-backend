from typing import Any

from fastapi import HTTPException as FastAPIHTTPException
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class APIError(FastAPIHTTPException):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(status, detail={"code": code, "message": message})


def error_response(
    request: Request, status: int, code: str, message: str, details: Any = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
        headers={"Cache-Control": "no-store"},
    )


async def http_error(request: Request, error: HTTPException) -> JSONResponse:
    detail = error.detail
    if isinstance(detail, dict):
        return error_response(request, error.status_code, detail["code"], detail["message"])
    return error_response(request, error.status_code, "http_error", str(detail))


async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    # Never echo request bodies/passwords into errors.
    details = [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]
    return error_response(request, 422, "validation_error", "請檢查輸入內容。", details)
