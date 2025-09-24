"""
Mindtrace UI — Theme

Owns:
- Component-level maps (COMPONENT_VARIANTS, SIZE_VARIANTS)

Depends on tokens via absolute import: mindtrace.ui.tokens
"""

from mindtrace.ui.tokens import FX, SH, SP, C, M, R, Ty

# ---- Size maps ----
SIZE_VARIANTS = {
    "input": {
        "small": {"padding": "0.5rem 0.75rem", "font_size": Ty.fs_sm},
        "medium": {"padding": "0.65rem 0.9rem", "font_size": Ty.fs_base},
        "large": {"padding": "0.75rem 1rem", "font_size": Ty.fs_lg},
    },
}

# ---- Component variants ----
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
            "font_family": Ty.font_sans,
            "font_size": Ty.fs_base,
            "border_radius": R.r_md,
            "background": C.surface,
            "border": f"1px solid {C.border}",
            "outline": "none",
            "transition": f"all {M.dur_fast} {M.ease}",
            "color": C.fg,
        },
        "focus": {
            "border_color": C.ring,
            "background": C.surface_2,
            "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
            "transform": "translateY(-1px)",
        },
        "hover": {"border_color": "rgba(0, 87, 255, 0.3)", "background": C.surface_2},
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
            "color": C.fg_muted,
            "cursor": "not-allowed",
        },
        "placeholder": {"color": C.fg_muted},
    },
    "select": {
        "base": {
            "width": "100%",
            "font_family": Ty.font_sans,
            "border_radius": R.r_md,
            "background": C.surface,
            "border": f"2px solid {C.accent}",
            "outline": "none",
            "transition": M.ease,
            "backdrop_filter": FX.backdrop_filter_light,
            "color": C.fg,
            "cursor": "pointer",
        },
        "compact": {
            "border": f"1px solid {C.border}",
            "background": C.surface,
            "backdrop_filter": "none",
            "border_radius": R.r_sm,
            "padding": "0.35rem 0.6rem",
            "font_size": Ty.fs_sm,
        },
        "focus": {
            "border_color": C.ring,
            "background": C.surface_2,
            "box_shadow": "0 0 0 4px rgba(0, 87, 255, 0.1), 0 4px 12px rgba(0, 87, 255, 0.15)",
            "transform": "translateY(-1px)",
        },
        "hover": {"border_color": "rgba(0, 87, 255, 0.3)", "background": C.surface_2},
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
            "color": C.fg_muted,
            "cursor": "not-allowed",
        },
    },
    "button": {
        "primary": {
            "background": C.accent,
            "color": C.accent_fg,
            "border": "none",
            "hover_background": "#0047E0",
            "hover_transform": "translateY(-1px)",
            "active_transform": "translateY(0)",
        },
        "secondary": {
            "background": C.surface,
            "color": C.fg,
            "border": f"1px solid {C.border}",
            "hover_background": C.surface_2,
            "hover_border_color": C.accent,
            "hover_color": C.accent,
        },
        "ghost": {
            "background": "transparent",
            "color": C.fg,
            "border": "none",
            "hover_background": "rgba(0, 87, 255, 0.08)",
            "hover_color": C.accent,
        },
        "danger": {
            "background": C.danger,
            "color": "#FFFFFF",
            "border": "none",
            "hover_background": "#DC2626",
            "hover_transform": "translateY(-1px)",
            "active_transform": "translateY(0)",
        },
        "outline": {
            "background": "transparent",
            "color": C.accent,
            "border": f"1px solid {C.accent}",
            "hover_background": "rgba(0, 87, 255, 0.08)",
            "hover_border_color": C.accent,
        },
        "base": {
            "font_weight": Ty.fw_500,
            "font_family": Ty.font_sans,
            "border_radius": R.r_md,
            "cursor": "pointer",
            "outline": "none",
            "transition": f"all {M.dur_fast} {M.ease}",
            "display": "inline-flex",
            "align_items": "center",
            "justify_content": "center",
            "gap": SP.space_2,
            "white_space": "nowrap",
            "user_select": "none",
            "position": "relative",
            "_focus_visible": {"outline": "none", "box_shadow": f"0 0 0 3px {C.ring}"},
            "_disabled": {"opacity": "0.5", "cursor": "not-allowed", "pointer_events": "none"},
        },
    },
    "header": {
        "title": {
            "font_size": Ty.fs_4xl,
            "font_weight": Ty.fw_700,
            "color": C.fg,
            "line_height": Ty.lh_normal,
            "font_family": Ty.font_sans,
            "letter_spacing": Ty.ls_tight,
            "text_align": "center",
        },
        "subtitle": {
            "font_size": Ty.fs_base,
            "font_weight": Ty.fw_400,
            "color": C.fg_muted,
            "line_height": Ty.lh_loose,
            "font_family": Ty.font_sans,
            "text_align": "center",
        },
    },
    "logo": {
        "title": {
            "font_size": Ty.fs_5xl,
            "font_weight": Ty.fw_700,
            "line_height": Ty.lh_normal,
            "font_family": Ty.font_sans,
            "letter_spacing": Ty.ls_normal,
            "color": C.accent,
            "margin": "0",
        },
        "subtitle": {
            "font_size": Ty.fs_xs,
            "font_weight": Ty.fw_500,
            "letter_spacing": Ty.ls_wide,
            "color": "rgba(100, 116, 139, 0.7)",
            "text_transform": "uppercase",
            "margin": "0",
            "font_family": Ty.font_sans,
        },
    },
    "loader": {
        "primary": {"color": C.accent, "background": f"{C.accent}20"},
        "danger": {"color": C.danger, "background": f"{C.danger}20"},
        "success": {"color": C.success, "background": f"{C.success}20"},
        "warning": {"color": C.warning, "background": f"{C.warning}20"},
        "info": {"color": C.info, "background": f"{C.info}20"},
    },
    "alert": {
        "base": {
            "display": "flex",
            "align_items": "center",
            "padding": SP.space_4,
            "border_radius": R.r_md,
            "font_family": Ty.font_sans,
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
        "error": {"background": "rgba(239, 68, 68, 0.1)", "border_color": "rgba(239, 68, 68, 0.3)", "color": "#991b1b"},
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
        "filled": {"border": "none"},
        "outlined": {"background": "transparent"},
        "soft": {"border": "none", "box_shadow": SH.shadow_1},
    },
}
