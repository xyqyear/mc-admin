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
from typing import Any, Callable, ParamSpec, TypeVar, cast

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
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = ", ".join(f"{k}={v!r}" for k, v in bound.arguments.items())
                return bound.arguments, f"[{params}] " if params else ""
            except Exception as e:
                logger.warning(
                    f"Failed to bind arguments for function {func_name}: {e}",
                    stacklevel=3,
                )
                parts = []
                if args:
                    parts.append(f"args={args!r}")
                if kwargs:
                    parts.append(f"kwargs={kwargs!r}")
                return {}, f"[{', '.join(parts)}] " if parts else ""

        def format_prefix(bound_args: dict) -> str:
            if not prefix:
                return ""

            if "{" in prefix and "}" in prefix:
                try:
                    formatted = prefix.format_map(bound_args)
                    return f"{formatted}: "
                except (KeyError, ValueError) as e:
                    logger.warning(
                        f"Failed to format prefix '{prefix}' with arguments: {e}",
                        stacklevel=3,
                    )
                    return f"{prefix}: "
            else:
                return f"{prefix}: "

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
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
                    return default_return

            return cast(Callable[P, R], async_wrapper)

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
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
                    return default_return

            return cast(Callable[P, R], sync_wrapper)

    return decorator
