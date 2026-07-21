"""
Central logging setup for DodoTheBot.

Provides a single configured logger used across the bot. Console output is
forced to UTF-8 so emoji in Discord messages never crash logging on Windows
consoles (which historically defaulted to cp1251 here), and everything is also
mirrored to a rotating file under ``logs/``.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "dodo.log")


class _ConsoleFormatter(logging.Formatter):
    """Compact, colorized formatter for the console."""

    _COLORS = {
        logging.DEBUG: "\x1b[38;20m",
        logging.INFO: "\x1b[34;20m",
        logging.WARNING: "\x1b[33;20m",
        logging.ERROR: "\x1b[31;20m",
        logging.CRITICAL: "\x1b[31;1m",
    }
    _RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelno, "")
        fmt = f"{color}[%(asctime)s] [%(levelname)-8s]{self._RESET} %(name)s: %(message)s"
        return logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S").format(record)


def setup_logger(name: str = "dodo", level: int = logging.INFO) -> logging.Logger:
    """Create (once) and return the shared bot logger."""
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger

    logger.setLevel(level)
    logger.propagate = False  # Don't duplicate records onto the root logger.

    # Force UTF-8 on stdout so emoji never raise UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ConsoleFormatter())
    logger.addHandler(console)

    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(file_handler)

    return logger
