"""
Component Variants for Poseidon

This module contains all component styling variants including
cards, inputs, buttons, headers, and logos.
"""

from .global_styles import COLORS, TYPOGRAPHY, SPACING, SIZING, EFFECTS, THEME as T

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
            "font_family": T.typography.font_sans,
            "font_size": T.typography.fs_base,
            "border_radius": T.radius.r_md,
            "background": T.colors.surface,
            "border": f"1px solid {T.colors.border}",
            "outline": "none",
            "transition": f"all {T.motion.dur_fast} {T.motion.ease}",
            "color": T.colors.fg,
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
        "error": {
            "border_color": COLORS["error"],
            "background": "rgba(239, 68, 68, 0.05)",
            "box_shadow": f"0 0 0 4px rgba(239, 68, 68, 0.1)",
        },
        "success": {
            "border_color": COLORS["success"],
            "background": "rgba(16, 185, 129, 0.05)",
            "box_shadow": f"0 0 0 4px rgba(16, 185, 129, 0.1)",
        },
        "disabled": {
            "background": "rgba(243, 244, 246, 0.8)",
            "border_color": "rgba(226, 232, 240, 0.8)",
            "color": COLORS["text_muted"],
            "cursor": "not-allowed",
        },
        "placeholder": {
            "color": COLORS["text_muted"],
        },
    },
    "select": {
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
            "cursor": "pointer",
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
        "error": {
            "border_color": COLORS["error"],
            "background": "rgba(239, 68, 68, 0.05)",
            "box_shadow": f"0 0 0 4px rgba(239, 68, 68, 0.1)",
        },
        "success": {
            "border_color": COLORS["success"],
            "background": "rgba(16, 185, 129, 0.05)",
            "box_shadow": f"0 0 0 4px rgba(16, 185, 129, 0.1)",
        },
        "disabled": {
            "background": "rgba(243, 244, 246, 0.8)",
            "border_color": "rgba(226, 232, 240, 0.8)",
            "color": COLORS["text_muted"],
            "cursor": "not-allowed",
        },
    },
    "button": {
        # Clean dashboard buttons using new tokens
        "primary": {
            "background": T.colors.accent,
            "color": T.colors.accent_fg,
            "border": "none",
            "hover_background": "#0047E0",  # Slightly darker
            "hover_transform": "translateY(-1px)",
            "active_transform": "translateY(0)",
        },
        "secondary": {
            "background": T.colors.surface,
            "color": T.colors.fg,
            "border": f"1px solid {T.colors.border}",
            "hover_background": T.colors.surface_2,
            "hover_border_color": T.colors.accent,
            "hover_color": T.colors.accent,
        },
        "ghost": {
            "background": "transparent",
            "color": T.colors.fg,
            "border": "none",
            "hover_background": "rgba(0, 87, 255, 0.08)",
            "hover_color": T.colors.accent,
        },
        "danger": {
            "background": T.colors.danger,
            "color": "#FFFFFF",
            "border": "none",
            "hover_background": "#DC2626",  # Slightly darker
            "hover_transform": "translateY(-1px)",
            "active_transform": "translateY(0)",
        },
        "outline": {
            "background": "transparent",
            "color": T.colors.accent,
            "border": f"1px solid {T.colors.accent}",
            "hover_background": "rgba(0, 87, 255, 0.08)",
            "hover_border_color": T.colors.accent,
        },
        # Base styles shared by all buttons
        "base": {
            "font_weight": T.typography.fw_500,
            "font_family": T.typography.font_sans,
            "border_radius": T.radius.r_md,
            "cursor": "pointer",
            "outline": "none",
            "transition": f"all {T.motion.dur_fast} {T.motion.ease}",
            "display": "inline-flex",
            "align_items": "center",
            "justify_content": "center",
            "gap": T.spacing.space_2,
            "white_space": "nowrap",
            "user_select": "none",
            "position": "relative",
            "_focus_visible": {
                "outline": "none",
                "box_shadow": f"0 0 0 3px {T.colors.ring}",
            },
            "_disabled": {
                "opacity": "0.5",
                "cursor": "not-allowed",
                "pointer_events": "none",
            },
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
    "loader": {
        "primary": {
            "color": COLORS["primary"],
            "background": f"{COLORS['primary']}20",
        },
        "secondary": {
            "color": COLORS["secondary"],
            "background": f"{COLORS['secondary']}20",
        },
        "danger": {
            "color": COLORS["danger"],
            "background": f"{COLORS['danger']}20",
        },
        "success": {
            "color": COLORS["success"],
            "background": f"{COLORS['success']}20",
        },
        "warning": {
            "color": COLORS["warning"],
            "background": f"{COLORS['warning']}20",
        },
        "info": {
            "color": COLORS["info"],
            "background": f"{COLORS['info']}20",
        },
    },
    "alert": {
        "base": {
            "display": "flex",
            "align_items": "center",
            "padding": SPACING["md"],
            "border_radius": SIZING["border_radius"]["md"],
            "font_family": TYPOGRAPHY["font_family"],
            "font_size": TYPOGRAPHY["font_sizes"]["sm"],
            "font_weight": TYPOGRAPHY["font_weights"]["medium"],
            "line_height": TYPOGRAPHY["line_heights"]["relaxed"],
            "border": "1px solid",
            "backdrop_filter": EFFECTS["backdrop_filter_light"],
            "transition": EFFECTS["transitions"]["normal"],
            "position": "relative",
            "overflow": "hidden",
        },
        "success": {
            "background": "rgba(16, 185, 129, 0.1)",
            "border_color": "rgba(16, 185, 129, 0.3)",
            "color": "#065f46",
        },
        "error": {
            "background": "rgba(239, 68, 68, 0.1)",
            "border_color": "rgba(239, 68, 68, 0.3)",
            "color": "#991b1b",
        },
        "warning": {
            "background": "rgba(245, 158, 11, 0.1)",
            "border_color": "rgba(245, 158, 11, 0.3)",
            "color": "#92400e",
        },
        "info": {
            "background": "rgba(59, 130, 246, 0.1)",
            "border_color": "rgba(59, 130, 246, 0.3)",
            "color": "#1e40af",
        },
        "filled": {
            "border": "none",
        },
        "outlined": {
            "background": "transparent",
        },
        "soft": {
            "border": "none",
            "box_shadow": EFFECTS["shadows"]["sm"],
        },
    },
}
