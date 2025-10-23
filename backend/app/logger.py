import functools
import gzip
import inspect
import logging
import logging.handlers
import os
import shutil
import sys
from gzip import GzipFile
from pathlib import Path
from typing import Callable

from .config import settings

logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s [%(module)s:%(funcName)s:%(lineno)d] %(message)s"
)

logs_dir = Path(settings.logs_dir)
logs_dir.mkdir(exist_ok=True)


def rotator(source, dest):
    with open(source, "rb") as f_in:
        with gzip.open(dest + ".gz", "wb") as f_out:
            assert isinstance(f_out, GzipFile)
            shutil.copyfileobj(f_in, f_out)
    os.remove(source)


log_file_handler = logging.handlers.TimedRotatingFileHandler(
    logs_dir / "app.log", when="midnight"
)
log_file_handler.setFormatter(formatter)
log_file_handler.rotator = rotator
logger.addHandler(log_file_handler)

log_stream_handler = logging.StreamHandler(sys.stdout)
log_stream_handler.setFormatter(formatter)
logger.addHandler(log_stream_handler)


def log_exception[**P, R](
    prefix: str = "",
    default_return: R | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to wrap a function with try-except and log exceptions.

    Supports both sync and async functions while preserving type signatures.
    The stacklevel is set to show the original function name and line number in logs.

    Args:
        prefix: Optional prefix to prepend to the error message

    Usage:
        @log_exception("MyOperation")
        async def my_async_func():
            ...

        @log_exception()
        def my_sync_func():
            ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # Get function signature for parameter binding
        sig = inspect.signature(func)
        func_name = func.__qualname__

        def format_args_kwargs(args: tuple, kwargs: dict) -> tuple[dict, str]:
            """
            Format function arguments for logging with parameter names.

            Returns:
                (bound_arguments_dict, formatted_string)
            """
            try:
                # Bind args and kwargs to function signature
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                # Format as param=value pairs
                params = ", ".join(f"{k}={v!r}" for k, v in bound.arguments.items())
                return bound.arguments, f"[{params}] " if params else ""
            except Exception as e:
                # Binding failed - log the failure
                logger.warning(
                    f"Failed to bind arguments for function {func_name}: {e}",
                    stacklevel=3,  # format_args_kwargs -> wrapper -> user code
                )
                # Fallback to simple args/kwargs format
                parts = []
                if args:
                    parts.append(f"args={args!r}")
                if kwargs:
                    parts.append(f"kwargs={kwargs!r}")
                return {}, f"[{', '.join(parts)}] " if parts else ""

        def format_prefix(bound_args: dict) -> str:
            """Format prefix with parameter substitution if braces present."""
            if not prefix:
                return ""

            # Check if prefix contains braces for parameter substitution
            if "{" in prefix and "}" in prefix:
                try:
                    # Use format_map for safe parameter substitution
                    formatted = prefix.format_map(bound_args)
                    return f"{formatted}: "
                except (KeyError, ValueError) as e:
                    logger.warning(
                        f"Failed to format prefix '{prefix}' with arguments: {e}",
                        stacklevel=3,  # format_prefix -> wrapper -> user code
                    )
                    return f"{prefix}: "
            else:
                return f"{prefix}: "

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    bound_args, args_str = format_args_kwargs(args, kwargs)
                    prefix_str = format_prefix(bound_args)
                    logger.error(
                        f"{args_str}{prefix_str}{type(e).__name__}: {e}",
                        exc_info=True,
                        stacklevel=2,
                    )
                    # Do not re-raise - swallow the exception and return None
                    return default_return  # type: ignore[return-value]

            return async_wrapper  # type: ignore[return-value]

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    bound_args, args_str = format_args_kwargs(args, kwargs)
                    prefix_str = format_prefix(bound_args)
                    logger.error(
                        f"{args_str}{prefix_str}{type(e).__name__}: {e}",
                        exc_info=True,
                        stacklevel=2,
                    )
                    # Do not re-raise - swallow the exception and return None
                    return default_return  # type: ignore[return-value]

            return sync_wrapper  # type: ignore[return-value]

    return decorator
