"""Minimalistic theme configuration for the Reflex app."""

import reflex as rx

# Simple color palette - black and orange only
COLORS = {
    "primary": "#ff6b00",           # Orange
    "background": "#000000",        # Black
    "surface": "#1a1a1a",          # Dark gray
    "text": "#ffffff",             # White
    "text_muted": "#a3a3a3",       # Gray
    "border": "#333333",           # Dark border
    "error": "#ff3333",            # Red
    "transparent": "transparent",   # Transparent
}

# Typography constants
TYPOGRAPHY = {
    "font_family": "Inter, system-ui, sans-serif",
    "font_sizes": {
        "xs": "0.75rem",    # 12px
        "sm": "0.875rem",   # 14px
        "base": "1rem",     # 16px
        "lg": "1.125rem",   # 18px
        "xl": "1.25rem",    # 20px
        "2xl": "1.5rem",    # 24px
        "3xl": "2rem",      # 32px
        "4xl": "3rem",      # 48px
    },
    "font_weights": {
        "normal": "400",
        "medium": "500",
        "semibold": "600",
        "bold": "700",
    },
}

# Spacing constants (using Reflex scale 0-9)
SPACING = {
    "xs": "1",      # 0.25rem
    "sm": "2",      # 0.5rem
    "md": "4",      # 1rem
    "lg": "6",      # 1.5rem
    "xl": "8",      # 2rem
}

# CSS spacing for direct use
CSS_SPACING = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2rem",
    "2xl": "3rem",
}

# Common sizing constants
SIZING = {
    "border_radius": "8px",
    "border_width": "1px",
    "max_width_form": "400px",
    "max_width_content": "600px",
    "full_height": "100vh",
    "container_height": "80vh",
}

# Theme configuration
theme_config = rx.theme(
    appearance="dark",
    accent_color="orange",
    gray_color="slate",
    radius="medium",
) 