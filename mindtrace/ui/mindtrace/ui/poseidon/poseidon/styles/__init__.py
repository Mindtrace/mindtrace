"""Simplified styling configuration.

This module provides essential styling for the Reflex app:
- Basic theme configuration for Reflex
- Minimal global styles for consistent typography
- Buridan UI components handle their own styling
"""

from .theme import theme_config
from .styles import styles

__all__ = [
    "theme_config",
    "styles",
] 