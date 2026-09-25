import logging
import logging.handlers
import sys
from pathlib import Path


class OwnedLogger(logging.Logger):
    def close(self) -> None:
        for handler in self.handlers[:]:
            handler.flush()
            handler.close()
            self.removeHandler(handler)


def file_logger(name: str, path: Path, *, audit: bool = False) -> OwnedLogger:
    logger = OwnedLogger(name, logging.INFO if audit else logging.DEBUG)
    logger.parent = logging.getLogger()
    logger.propagate = not audit
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(message)s" if audit else
        "%(asctime)s %(levelname)s [%(module)s:%(funcName)s:%(lineno)d] %(message)s"
    )
    file_handler = logging.handlers.TimedRotatingFileHandler(
        path, when="midnight", encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if not audit:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger
