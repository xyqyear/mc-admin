import functools
import gzip
import os
import shutil
from collections.abc import Awaitable, Callable, Coroutine
from gzip import GzipFile
from logging.handlers import TimedRotatingFileHandler
from typing import Any

from .config import get_settings
from .runtime_logging import OwnedLogger, file_logger
from .runtime_resources import current_runtime


def rotator(source, dest):
    with open(source, "rb") as f_in, gzip.open(dest + ".gz", "wb") as f_out:
        assert isinstance(f_out, GzipFile)
        shutil.copyfileobj(f_in, f_out)
    os.remove(source)


def create_logger() -> OwnedLogger:
    settings = get_settings()
    result = file_logger("app", settings.logs_dir / "app.log")
    for handler in result.handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            handler.rotator = rotator
    return result


def get_logger() -> OwnedLogger:
    return current_runtime().app_logger


def log_exception[**P, R](
    prefix: str = "",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Coroutine[Any, Any, R | None]]]:

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[Any, Any, R | None]]:
        context = prefix or f"Operation {func.__qualname__} failed"

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            logger = get_logger()
            try:
                return await func(*args, **kwargs)
            except Exception as error:  # noqa: BLE001 - ordinary failures must leave async consumers running
                from .errors import log_safe_error
                log_safe_error(error, context, logger=logger)
                return None

        return async_wrapper

    return decorator
