"""
Centralized logging configuration for Odin.

Environment Variables:
    ODIN_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                     Default: WARNING
    ODIN_LOG_FORMAT: Custom log format string
    ODIN_LOG_FILE: Path to log file (if set, logs go to file too)
"""

import contextvars
import logging
import os
from typing import Optional

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injects request_id from contextvars into every log record."""

    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


def get_log_level() -> int:
    """Get log level from environment variable."""
    level_str = os.environ.get("ODIN_LOG_LEVEL", "INFO").upper()
    
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    
    return level_map.get(level_str, logging.WARNING)


def get_log_format() -> str:
    """Get log format from environment variable."""
    custom_format = os.environ.get("ODIN_LOG_FORMAT")
    if custom_format:
        return custom_format
    
    # Default format with timestamp, level, logger name, and message
    return (
        "%(asctime)s [%(levelname)-8s] [%(request_id)s] %(name)s: %(message)s"
    )


def setup_logging(
    log_level: Optional[int] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return the root Odin logger.
    
    Args:
        log_level: Override default level (from env var)
        log_file: Path to log file for file logging
        
    Returns:
        Configured root logger for 'odin'
    """
    # Get configuration from environment or arguments
    effective_level = log_level if log_level is not None else get_log_level()
    log_format = get_log_format()
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    
    # Configure root logger for odin package
    root_logger = logging.getLogger("odin")
    root_logger.setLevel(effective_level)
    
    # Clear existing handlers to avoid duplicates on re-import
    root_logger.handlers.clear()

    # Console handler (always enabled)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIdFilter())
    root_logger.addHandler(console_handler)
    
    # File handler (if log file specified)
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file, mode='a')
            file_handler.setFormatter(formatter)
            file_handler.addFilter(RequestIdFilter())
            root_logger.addHandler(file_handler)
        except OSError as e:
            # If we can't create the log file, just warn and continue with console
            logging.warning(f"Could not setup file logging: {e}")
    
    return root_logger


def get_component_logger(component_name: str) -> logging.Logger:
    """
    Get a logger for a specific component.
    
    Args:
        component_name: Component identifier (e.g., 'ir', 'query', 'executor')
        
    Returns:
        Logger instance with name 'odin.{component_name}'
    """
    return logging.getLogger(f"odin.{component_name}")


def get_uvicorn_log_config() -> dict:
    """Return a uvicorn log config dict that matches Odin's format."""
    log_format = get_log_format()
    level = get_log_level()
    level_name = logging.getLevelName(level)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": lambda: RequestIdFilter()},
        },
        "formatters": {
            "odin": {"format": log_format},
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
ROOT_LOGGER = setup_logging()
