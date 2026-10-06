import functools
import gzip
import inspect
import os
import shutil
from collections.abc import Callable
from gzip import GzipFile
from logging.handlers import TimedRotatingFileHandler
from typing import Any, ParamSpec, TypeVar, cast

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


P = ParamSpec("P")
R = TypeVar("R")


def log_exception(
    prefix: str = "",
    default_return: Any = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log safe failure context and return the configured fallback."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        context = prefix or f"Operation {func.__qualname__} failed"

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                logger = get_logger()
                try:
                    return await func(*args, **kwargs)
                except Exception as error:  # noqa: BLE001 - decorated operations preserve their configured failure return
                    from .errors import log_safe_error
                    log_safe_error(error, context, logger=logger)
                    return default_return

            return cast(Callable[P, R], async_wrapper)

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                logger = get_logger()
                try:
                    return func(*args, **kwargs)
                except Exception as error:  # noqa: BLE001 - decorated operations preserve their configured failure return
                    from .errors import log_safe_error
                    log_safe_error(error, context, logger=logger)
                    return default_return

            return cast(Callable[P, R], sync_wrapper)

    return decorator
