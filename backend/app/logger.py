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
    return current_runtime().resource('app_logger')


P = ParamSpec("P")
R = TypeVar("R")


def log_exception(
    prefix: str = "",
    default_return: Any = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Wrap a sync or async function: log exceptions and return ``default_return``."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        sig = inspect.signature(func)
        func_name = func.__qualname__

        def format_args_kwargs(
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> tuple[dict[str, Any], str]:
            logger = get_logger()
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = ", ".join(f"{k}={v!r}" for k, v in bound.arguments.items())
                return bound.arguments, f"[{params}] " if params else ""
            except Exception as e:
                logger.warning(
                    f"Failed to bind arguments for function {func_name}: {e}",
                    stacklevel=4, exc_info=True)
                parts = []
                if args:
                    parts.append(f"args={args!r}")
                if kwargs:
                    parts.append(f"kwargs={kwargs!r}")
                return {}, f"[{', '.join(parts)}] " if parts else ""

        def format_prefix(bound_args: dict) -> str:
            logger = get_logger()
            if not prefix:
                return ""

            if "{" in prefix and "}" in prefix:
                try:
                    formatted = prefix.format_map(bound_args)
                    return f"{formatted}: "
                except (KeyError, ValueError) as e:
                    logger.warning(
                        f"Failed to format prefix '{prefix}' with arguments: {e}",
                        stacklevel=4,
                    )
                    return f"{prefix}: "
            else:
                return f"{prefix}: "

        def format_failure_message(
            error: Exception, args: tuple[Any, ...], kwargs: dict[str, Any]
        ) -> str:
            bound_args, args_str = format_args_kwargs(args, kwargs)
            prefix_str = format_prefix(bound_args)
            return f"{args_str}{prefix_str}{type(error).__name__}: {error}"

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                logger = get_logger()
                try:
                    return await func(*args, **kwargs)
                except Exception as error:
                    message = format_failure_message(error, args, kwargs)
                    logger.exception(
                        message,
                        stacklevel=2,
                    )
                    return default_return

            return cast(Callable[P, R], async_wrapper)

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                logger = get_logger()
                try:
                    return func(*args, **kwargs)
                except Exception as error:
                    message = format_failure_message(error, args, kwargs)
                    logger.exception(
                        message,
                        stacklevel=2,
                    )
                    return default_return

            return cast(Callable[P, R], sync_wrapper)

    return decorator
