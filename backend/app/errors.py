"""Public operation failures and diagnostics without exception values or locals."""

import json
import re
from traceback import extract_tb
from typing import Any

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logger import get_logger

INTERNAL_ERROR_MESSAGE = "服务器内部错误，请稍后重试"


class PublicOperationError(RuntimeError):
    """An authored, safe user message; never wrap raw adapter exceptions or stderr."""


def public_error_detail(error: Exception) -> Any:
    if isinstance(error, HTTPException):
        return error.detail
    if isinstance(error, PublicOperationError):
        return str(error)
    return INTERNAL_ERROR_MESSAGE


def public_error_message(error: Exception) -> str:
    detail = public_error_detail(error)
    if isinstance(detail, dict) and public_error_code(error) and isinstance(detail.get("message"), str):
        return detail["message"]
    return detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)


def public_error_code(error: Exception) -> str | None:
    detail = public_error_detail(error)
    code = detail.get("code") if isinstance(detail, dict) else None
    return code if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) else None


def log_safe_error(error: Exception, context: str) -> None:
    logger = get_logger()
    frames = ", ".join(
        f"{frame.name}:{frame.lineno}"
        for frame in extract_tb(error.__traceback__)[-10:]
    )
    logger.error("%s: %s; stack=%s", context, type(error).__name__, frames)


class SafeErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def observe(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, observe)
        except Exception as exc:  # noqa: BLE001 - exception values can contain credentials
            log_safe_error(exc, "HTTP request failed")
            if started:
                # A started stream cannot be replaced with a JSON error response.
                raise RuntimeError("服务器响应中断") from None
            response = JSONResponse(
                status_code=exc.status_code if isinstance(exc, HTTPException) else 500,
                content={"detail": public_error_detail(exc)},
                headers=exc.headers if isinstance(exc, HTTPException) else None,
            )
            await response(scope, receive, send)
