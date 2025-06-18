"""Minimalistic styling configuration.

This module provides a complete styling system with:
- Theme configuration and color palette
- Typography and spacing constants  
- Component styles and button variants
- All constants to eliminate hardcoded values
"""

from .theme import theme_config, COLORS, TYPOGRAPHY, SPACING, CSS_SPACING, SIZING
from .styles import (
    styles, button_variants, input_variants, card_variants,
    BOX_SHADOWS, TRANSITIONS, HEIGHTS, WIDTHS
)

__all__ = [
    "theme_config",
    "styles",
    "button_variants",
    "input_variants",
    "card_variants",
    "COLORS",
    "TYPOGRAPHY",
    "SPACING",
    "CSS_SPACING",
    "SIZING",
    "BOX_SHADOWS",
    "TRANSITIONS",
    "HEIGHTS",
    "WIDTHS",
] 