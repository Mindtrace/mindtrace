"""
Component Variants for Poseidon

This module contains all component styling variants including
cards, inputs, buttons, headers, and logos.
"""

from .global_styles import COLORS, TYPOGRAPHY, SPACING, SIZING, EFFECTS

# Component Variants
COMPONENT_VARIANTS = {
    "card": {
        "base": {
            "background": COLORS["background_card"],
            "backdrop_filter": EFFECTS["backdrop_filter"],
            "border_radius": SIZING["border_radius"]["xl"],
            "border": f"1px solid {COLORS['border_card']}",
            "box_shadow": EFFECTS["shadows"]["lg"],
            "padding": SPACING["xl"],
            "position": "relative",
            "overflow": "hidden",
        },
    },
    "input": {
        "base": {
            "width": "100%",
            "font_family": TYPOGRAPHY["font_family"],
            "border_radius": SIZING["border_radius"]["md"],
            "background": COLORS["background_input"],
            "border": f"2px solid {COLORS['border_primary']}",
            "outline": "none",
            "transition": EFFECTS["transitions"]["normal"],
            "backdrop_filter": EFFECTS["backdrop_filter_light"],
            "color": COLORS["text_primary"],
        },
        "focus": {
            "border_color": COLORS["border_focus"],
            "background": COLORS["background_input_focus"],
            "box_shadow": f"0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
            "transform": "translateY(-1px)",
        },
        "hover": {
            "border_color": "rgba(0, 87, 255, 0.3)",
            "background": COLORS["background_input_focus"],
        },
        "placeholder": {
            "color": COLORS["text_muted"],
        },
    },
    "button": {
        "primary": {
            "background": f"linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_dark']} 100%)",
            "hover_background": f"linear-gradient(135deg, {COLORS['primary_dark']} 0%, #003399 100%)",
            "shadow": EFFECTS["shadows"]["xl"],
            "hover_shadow": "0 8px 24px rgba(0, 87, 255, 0.4)",
        },
        "danger": {
            "background": f"linear-gradient(135deg, {COLORS['danger']} 0%, {COLORS['danger_dark']} 100%)",
            "hover_background": f"linear-gradient(135deg, {COLORS['danger_dark']} 0%, #991B1B 100%)",
            "shadow": EFFECTS["shadows"]["danger"],
            "hover_shadow": "0 8px 24px rgba(220, 38, 38, 0.4)",
        },
        "base": {
            "width": "100%",
            "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
            "font_family": TYPOGRAPHY["font_family"],
            "border_radius": SIZING["border_radius"]["md"],
            "color": COLORS["white"],
            "border": "none",
            "cursor": "pointer",
            "transition": EFFECTS["transitions"]["normal"],
            "position": "relative",
            "overflow": "hidden",
            "outline": "none",
        },
    },
    "header": {
        "title": {
            "font_size": TYPOGRAPHY["font_sizes"]["4xl"],
            "font_weight": TYPOGRAPHY["font_weights"]["bold"],
            "color": COLORS["text_primary"],
            "line_height": TYPOGRAPHY["line_heights"]["normal"],
            "font_family": TYPOGRAPHY["font_family"],
            "letter_spacing": TYPOGRAPHY["letter_spacing"]["tight"],
            "text_align": "center",
        },
        "subtitle": {
            "font_size": TYPOGRAPHY["font_sizes"]["base"],
            "font_weight": TYPOGRAPHY["font_weights"]["normal"],
            "color": COLORS["text_secondary"],
            "line_height": TYPOGRAPHY["line_heights"]["loose"],
            "font_family": TYPOGRAPHY["font_family"],
            "text_align": "center",
        },
    },
    "logo": {
        "title": {
            "font_size": TYPOGRAPHY["font_sizes"]["5xl"],
            "font_weight": TYPOGRAPHY["font_weights"]["bold"],
            "line_height": TYPOGRAPHY["line_heights"]["tight"],
            "font_family": TYPOGRAPHY["font_family"],
            "letter_spacing": TYPOGRAPHY["letter_spacing"]["normal"],
            "color": COLORS["primary"],
            "margin": "0",
        },
        "subtitle": {
            "font_size": TYPOGRAPHY["font_sizes"]["xs"],
            "font_weight": TYPOGRAPHY["font_weights"]["medium"],
            "letter_spacing": TYPOGRAPHY["letter_spacing"]["wide"],
            "color": "rgba(100, 116, 139, 0.7)",
            "text_transform": "uppercase",
            "margin": "0",
            "font_family": TYPOGRAPHY["font_family"],
        },
    },
} 