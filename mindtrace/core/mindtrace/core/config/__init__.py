"""
Core configuration module for Mindtrace project.

Provides centralized configuration management with support for directory paths,
environment variables, and JSON file loading/saving.
"""

from mindtrace.core.config.config import Config, get_config

__all__ = ["Config", "get_config"]
