from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 404:
            code, message = "not_found", "请求的资源不存在"
        elif error.status_code == 405:
            code, message = "method_not_allowed", "请求方法不受支持"
        else:
            code, message = "http_error", "请求无法处理"
        return JSONResponse(
            status_code=error.status_code,
            content={"code": code, "message": message, "details": {}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        fields = sorted(
            {
                str(location[-1])
                for item in error.errors()
                if (location := item.get("loc")) and location[-1] != "body"
            }
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "请求参数不完整或格式不正确",
                "details": {"fields": fields},
            },
        )
