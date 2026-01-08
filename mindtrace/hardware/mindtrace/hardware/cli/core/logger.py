"""Logging configuration for the CLI using Rich."""

import logging
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.theme import Theme

# Custom theme for professional CLI output
CLI_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "progress": "cyan",
    }
)


def setup_logger(
    name: str = "mindtrace-hw-cli", log_file: Optional[Path] = None, verbose: bool = False
) -> logging.Logger:
    """Set up logger for the CLI.

    Args:
        name: Logger name
        log_file: Optional log file path
        verbose: Enable verbose logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Set level based on verbosity
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Simple format for console
    console_format = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


class RichLogger:
    """Logger that uses Rich Console for professional output."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize RichLogger.

        Args:
            console: Optional Rich Console instance. Creates new one if not provided.
        """
        self.console = console or Console(theme=CLI_THEME)
        self.error_console = Console(stderr=True, theme=CLI_THEME)

    def info(self, message: str):
        """Log info message.

        Args:
            message: Message to log
        """
        self.console.print(message, style="info")

    def success(self, message: str):
        """Log success message.

        Args:
            message: Success message to log
        """
        self.console.print(f"[✓] {message}", style="success")

    def warning(self, message: str):
        """Log warning message.

        Args:
            message: Warning message to log
        """
        self.console.print(f"[!] {message}", style="warning")

    def error(self, message: str):
        """Log error message.

        Args:
            message: Error message to log
        """
        self.error_console.print(f"[✗] {message}", style="error")

    def progress(self, message: str):
        """Log progress message.

        Args:
            message: Progress message to log
        """
        self.console.print(f"[~] {message}", style="progress")
