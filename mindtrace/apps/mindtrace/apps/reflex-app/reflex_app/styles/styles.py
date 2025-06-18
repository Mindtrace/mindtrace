"""Minimalistic styles for the Reflex app.

This module provides a unified styling system with:
- Global styles for consistent appearance
- Component-specific styles following design system
- Button variants for different use cases
- All styling values sourced from theme constants
"""

import reflex as rx
from .theme import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING

# Essential styles only - no hardcoded values
styles = {
    # Global styles
    "body": {
        "background_color": COLORS["background"],
        "color": COLORS["text"],
        "font_family": TYPOGRAPHY["font_family"],
        "margin": "0",
        "padding": "0",
    },
    
    # Component styles
    rx.input: {
        "background_color": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text"],
        "padding": f"{CSS_SPACING['sm']} {CSS_SPACING['md']}",
        "_focus": {"border_color": COLORS["primary"]},
        "_hover": {"border_color": COLORS["primary"]},
    },
    
    rx.button: {
        "background_color": COLORS["primary"],
        "color": COLORS["background"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{CSS_SPACING['sm']} {CSS_SPACING['md']}",
        "font_weight": TYPOGRAPHY["font_weights"]["medium"],
        "transition": "all 0.2s ease",
        "_hover": {"opacity": "0.8"},
    },
    
    rx.link: {
        "color": COLORS["primary"],
        "text_decoration": "none",
        "transition": "all 0.2s ease",
        "_hover": {"text_decoration": "underline"},
    },
    
    rx.heading: {
        "color": COLORS["text"],
        "font_weight": TYPOGRAPHY["font_weights"]["bold"],
        "line_height": "1.2",
    },
    
    rx.text: {
        "color": COLORS["text"],
        "line_height": "1.5",
    },
}

# Button variants following design system
button_variants = {
    "primary": {
        "background_color": COLORS["primary"],
        "color": COLORS["background"],
        "border": "none",
        "_hover": {
            "opacity": "0.9",
            "transform": "translateY(-1px)",
        },
    },
    "secondary": {
        "background_color": "transparent",
        "border": f"{SIZING['border_width']} solid {COLORS['primary']}",
        "color": COLORS["primary"],
        "_hover": {
            "background_color": COLORS["primary"],
            "color": COLORS["background"],
        },
    },
    "ghost": {
        "background_color": "transparent",
        "border": "none",
        "color": COLORS["text"],
        "_hover": {
            "background_color": COLORS["surface"],
        },
    },
}

# Box shadows for depth and elevation
BOX_SHADOWS = {
    "sm": "0 1px 2px rgba(0, 0, 0, 0.05)",
    "md": "0 4px 6px rgba(0, 0, 0, 0.1)",
    "lg": "0 8px 16px rgba(0, 0, 0, 0.2)",
    "xl": "0 20px 25px rgba(0, 0, 0, 0.15)",
}

# Transitions for smooth animations
TRANSITIONS = {
    "fast": "all 0.1s ease",
    "normal": "all 0.2s ease",
    "slow": "all 0.3s ease",
}

# Height utilities
HEIGHTS = {
    "screen_80": "80vh",
    "screen_full": "100vh",
}

# Width utilities  
WIDTHS = {
    "full": "100%",
    "form_input": "100%",
}

# Input variants for different use cases
input_variants = {
    "default": {
        "background_color": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text"],
        "padding": f"{CSS_SPACING['sm']} {CSS_SPACING['md']}",
        "_focus": {"border_color": COLORS["primary"]},
        "_hover": {"border_color": COLORS["primary"]},
    },
    "error": {
        "background_color": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['error']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text"],
        "padding": f"{CSS_SPACING['sm']} {CSS_SPACING['md']}",
        "_focus": {"border_color": COLORS["error"]},
    },
}

# Card variants for different content containers
card_variants = {
    "default": {
        "background": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "padding": CSS_SPACING["xl"],
        "box_shadow": BOX_SHADOWS["md"],
    },
    "elevated": {
        "background": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "padding": CSS_SPACING["xl"],
        "box_shadow": BOX_SHADOWS["lg"],
    },
    "flat": {
        "background": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "padding": CSS_SPACING["xl"],
    },
} 