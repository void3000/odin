"""
Centralized logging configuration for Odin.

Environment Variables:
    ODIN_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO
    ODIN_LOG_FORMAT: Custom log format string
    ODIN_LOG_FILE: Path to log file (if set, logs also write to file)
"""

import contextvars
import logging
import os
from typing import Optional

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s [%(levelname)-8s] [%(request_id)s] %(name)s: %(message)s"


class RequestIdFilter(logging.Filter):
    """Injects request_id from contextvars into every log record."""

    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


def _make_handler(handler: logging.Handler, formatter: logging.Formatter) -> logging.Handler:
    """Apply the standard formatter and request-id filter to a handler."""
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    return handler


def setup_logging(
    log_level: Optional[int] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Configure and return the root Odin logger.

    Safe to call multiple times — clears previous handlers first.
    """
    level = log_level if log_level is not None else logging.getLevelName(
        os.environ.get("ODIN_LOG_LEVEL", "INFO").upper()
    )
    fmt = os.environ.get("ODIN_LOG_FORMAT", LOG_FORMAT)
    log_file = log_file or os.environ.get("ODIN_LOG_FILE")

    formatter = logging.Formatter(fmt)

    root_logger = logging.getLogger("odin")
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    root_logger.addHandler(_make_handler(logging.StreamHandler(), formatter))

    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            root_logger.addHandler(
                _make_handler(logging.FileHandler(log_file, mode="a"), formatter)
            )
        except OSError as e:
            root_logger.warning(f"Could not setup file logging: {e}")

    return root_logger


def get_component_logger(component_name: str) -> logging.Logger:
    """Get a logger for a specific component (e.g. 'odin.executor')."""
    return logging.getLogger(f"odin.{component_name}")


def get_uvicorn_log_config() -> dict:
    """Return a uvicorn log config dict that matches Odin's format."""
    fmt = os.environ.get("ODIN_LOG_FORMAT", LOG_FORMAT)
    level_name = os.environ.get("ODIN_LOG_LEVEL", "INFO").upper()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": RequestIdFilter},
        },
        "formatters": {
            "odin": {"format": fmt},
        },
        "handlers": {
            "default": {
                "formatter": "odin",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "filters": ["request_id"],
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level_name, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": level_name, "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": level_name, "propagate": False},
        },
    }


# Initialize root logger on module import
setup_logging()
