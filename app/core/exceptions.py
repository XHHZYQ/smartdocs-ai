# app/core/exceptions.py
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class BusinessException(Exception):
    """业务异常，主动 raise 时用，例如 raise BusinessException("标题不能为空")"""

    def __init__(self, msg: str, code: int = 1, status_code: int = 400):
        self.code = code
        self.msg = msg
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessException)
    async def business_exception_handler(request: Request, exc: BusinessException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "data": None, "msg": exc.msg},
        )

    # 兜住你现有 documents.py 里的 raise HTTPException(...)
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "data": None, "msg": exc.detail},
        )

    # Pydantic 校验失败（比如 payload 少传字段）
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "data": None,
                "msg": "参数校验失败",
                "errors": exc.errors(),
            },
        )

    # 兜底：没被上面捕获的所有异常（相当于 Fastify 的 default error handler）
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"code": 500, "data": None, "msg": "服务器内部错误"},
        )
