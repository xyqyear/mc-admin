import logging
import logging.handlers
import sys
from pathlib import Path

from .config import settings

logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s [%(module)s:%(funcName)s:%(lineno)d] %(message)s"
)

logs_dir = Path(settings.logs_dir)
logs_dir.mkdir(exist_ok=True)

log_file_handler = logging.handlers.TimedRotatingFileHandler(
    logs_dir / "app.log", when="midnight"
)
log_file_handler.setFormatter(formatter)
logger.addHandler(log_file_handler)

log_stream_handler = logging.StreamHandler(sys.stdout)
log_stream_handler.setFormatter(formatter)
logger.addHandler(log_stream_handler)
