"""Logging configuration for the CLI."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click


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

    # Console handler with color support
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


class ClickLogger:
    """Logger that uses click.echo for output."""

    @staticmethod
    def info(message: str):
        """Log info message."""
        click.echo(message)

    @staticmethod
    def success(message: str):
        """Log success message with green color."""
        click.echo(click.style(f"✅ {message}", fg="green"))

    @staticmethod
    def warning(message: str):
        """Log warning message with yellow color."""
        click.echo(click.style(f"⚠️  {message}", fg="yellow"))

    @staticmethod
    def error(message: str):
        """Log error message with red color."""
        click.echo(click.style(f"❌ {message}", fg="red"), err=True)

    @staticmethod
    def progress(message: str):
        """Log progress message."""
        click.echo(click.style(f"🚀 {message}", fg="cyan"))
