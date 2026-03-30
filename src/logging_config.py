"""
Centralized logging configuration for Odin.

Environment Variables:
    ODIN_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                     Default: WARNING
    ODIN_LOG_FORMAT: Custom log format string
    ODIN_LOG_FILE: Path to log file (if set, logs go to file too)
"""

import logging
import os
from typing import Optional


def get_log_level() -> int:
    """Get log level from environment variable."""
    level_str = os.environ.get("ODIN_LOG_LEVEL", "WARNING").upper()
    
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
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
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
    root_logger.addHandler(console_handler)
    
    # File handler (if log file specified)
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file, mode='a')
            file_handler.setFormatter(formatter)
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


# Initialize root logger on module import
ROOT_LOGGER = setup_logging()
