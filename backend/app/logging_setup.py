"""Structlog configuration — console + file output."""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from app.config import settings

LOG_DIR = Path("/app/logs") if Path("/app").exists() else Path("logs")


def setup_logging() -> None:
    """Configure structlog with console + rotating file output."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared structlog processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # File handler — JSON lines, rotating 10 MB x 3 files
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "saga.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Configure stdlib logging (catches uvicorn, sqlalchemy, etc.)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Formatter for file: JSON lines (full, not truncated)
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )
    file_handler.setFormatter(file_formatter)

    # Formatter for console: key=value (human-readable)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
    )
    console_handler.setFormatter(console_formatter)
