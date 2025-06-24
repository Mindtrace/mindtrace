"""Modern dashboard styling configuration.

This module provides a comprehensive styling system with:
- Modern light theme configuration and color palette
- Typography and spacing constants following design system
- Component variants for cards, buttons, sidebar, header
- Grid layouts and utility classes
- All constants to eliminate hardcoded values
"""

from .theme import (
    theme_config, COLORS, TYPOGRAPHY, SPACING, SIZING, SHADOWS
)
from .styles import (
    styles, button_variants, input_variants, card_variants,
    sidebar_variants, header_variants, content_variants, 
    grid_variants, utilities
)

__all__ = [
    # Theme configuration
    "theme_config",
    
    # Global styles
    "styles",
    
    # Component variants
    "button_variants",
    "input_variants", 
    "card_variants",
    "sidebar_variants",
    "header_variants",
    "content_variants",
    "grid_variants",
    "utilities",
    
    # Theme constants
    "COLORS",
    "TYPOGRAPHY",
    "SPACING",
    "SIZING",
    "SHADOWS",
] 