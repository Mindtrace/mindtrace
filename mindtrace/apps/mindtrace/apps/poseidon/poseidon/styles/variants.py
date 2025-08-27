"""
Component Variants for Poseidon

This module contains all component styling variants including
cards, inputs, buttons, headers, and logos.
"""

from .global_styles import FX, SH, SP, C, M, R, Ty
from .global_styles import THEME as T

# Component Variants
COMPONENT_VARIANTS = {
    "card": {
        "base": {
            "background": C.bg,
            "backdrop_filter": FX.backdrop_filter,
            "border_radius": R.r_xl,
            "border": f"1px solid {C.border}",
            "box_shadow": SH.shadow_2,
            "padding": SP.space_10,
            "position": "relative",
            "overflow": "hidden",
        },
    },
    "input": {
        "base": {
            "width": "100%",
            "font_family": T.typography.font_sans,
            "font_size": T.typography.fs_base,
            "border_radius": R.r_md,
            "background": T.colors.surface,
            "border": f"1px solid {T.colors.border}",
            "outline": "none",
            "transition": f"all {T.motion.dur_fast} {T.motion.ease}",
            "color": T.colors.fg,
        },
        "focus": {
            "border_color": C.ring,
            "background": T.colors.surface_2,
            "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
            "transform": "translateY(-1px)",
        },
        "hover": {
            "border_color": "rgba(0, 87, 255, 0.3)",
            "background": T.colors.surface_2,
        },
        "error": {
            "border_color": C.danger,
            "background": "rgba(239, 68, 68, 0.05)",
            "box_shadow": "0 0 0 4px rgba(239, 68, 68, 0.1)",
        },
        "success": {
            "border_color": C.success,
            "background": "rgba(16, 185, 129, 0.05)",
            "box_shadow": "0 0 0 4px rgba(16, 185, 129, 0.1)",
        },
        "disabled": {
            "background": "rgba(243, 244, 246, 0.8)",
            "border_color": "rgba(226, 232, 240, 0.8)",
            "color": T.colors.fg_muted,
            "cursor": "not-allowed",
        },
        "placeholder": {
            "color": T.colors.fg_muted,
        },
    },
    "select": {
        "base": {
            "width": "100%",
            "font_family": T.typography.font_sans,
            "border_radius": R.r_md,
            "background": T.colors.surface,
            "border": f"2px solid {T.colors.accent}",
            "outline": "none",
            "transition": M.ease,
            "backdrop_filter": FX.backdrop_filter_light,
            "color": T.colors.fg,
            "cursor": "pointer",
        },
        "compact": {
            "border": f"1px solid {T.colors.border}",
            "background": T.colors.surface,
            "backdrop_filter": "none",
            "border_radius": R.r_sm,
            "padding": "0.35rem 0.6rem",
            "font_size": Ty.fs_sm,
        },
        "focus": {
            "border_color": C.ring,
            "background": T.colors.surface_2,
            "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
            "transform": "translateY(-1px)",
        },
        "hover": {
            "border_color": "rgba(0, 87, 255, 0.3)",
            "background": T.colors.surface_2,
        },
        "error": {
            "border_color": C.danger,
            "background": "rgba(239, 68, 68, 0.05)",
            "box_shadow": "0 0 0 4px rgba(239, 68, 68, 0.1)",
        },
        "success": {
            "border_color": C.success,
            "background": "rgba(16, 185, 129, 0.05)",
            "box_shadow": "0 0 0 4px rgba(16, 185, 129, 0.1)",
        },
        "disabled": {
            "background": "rgba(243, 244, 246, 0.8)",
            "border_color": "rgba(226, 232, 240, 0.8)",
            "color": T.colors.fg_muted,
            "cursor": "not-allowed",
        },
    },
    "button": {
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
            "font_size": Ty.fs_4xl,
            "font_weight": Ty.fw_700,
            "color": T.colors.fg,
            "line_height": Ty.lh_normal,
            "font_family": T.typography.font_sans,
            "letter_spacing": Ty.ls_tight,
            "text_align": "center",
        },
        "subtitle": {
            "font_size": Ty.fs_base,
            "font_weight": Ty.fw_400,
            "color": T.colors.fg_muted,
            "line_height": Ty.lh_loose,
            "font_family": T.typography.font_sans,
            "text_align": "center",
        },
    },
    "logo": {
        "title": {
            "font_size": Ty.fs_5xl,
            "font_weight": Ty.fw_700,
            "line_height": Ty.lh_normal,
            "font_family": T.typography.font_sans,
            "letter_spacing": Ty.ls_normal,
            "color": T.colors.accent,
            "margin": "0",
        },
        "subtitle": {
            "font_size": Ty.fs_xs,
            "font_weight": Ty.fw_500,
            "letter_spacing": Ty.ls_wide,
            "color": "rgba(100, 116, 139, 0.7)",
            "text_transform": "uppercase",
            "margin": "0",
            "font_family": T.typography.font_sans,
        },
    },
    "loader": {
        "primary": {
            "color": T.colors.accent,
            "background": f"{T.colors.accent}20",
        },
        "danger": {
            "color": C.danger,
            "background": f"{C.danger}20",
        },
        "success": {
            "color": C.success,
            "background": f"{C.success}20",
        },
        "warning": {
            "color": C.warning,
            "background": f"{C.warning}20",
        },
        "info": {
            "color": C.info,
            "background": f"{C.info}20",
        },
    },
    "alert": {
        "base": {
            "display": "flex",
            "align_items": "center",
            "padding": SP.space_4,
            "border_radius": R.r_md,
            "font_family": T.typography.font_sans,
            "font_size": Ty.fs_sm,
            "font_weight": Ty.fw_500,
            "line_height": Ty.lh_loose,
            "border": "1px solid",
            "backdrop_filter": FX.backdrop_filter_light,
            "transition": M.ease,
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
            "box_shadow": SH.shadow_1,
        },
    },
}
