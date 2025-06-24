"""Enhanced dashboard styles for the Reflex app.

This module provides a comprehensive styling system for a premium dashboard:
- Enhanced global styles with Google Fonts integration
- Premium component styling with smooth animations
- Advanced card variants with gradients and depth
- Modern sidebar and navigation styles
- All styling values sourced from enhanced theme constants
"""

import reflex as rx
from poseidon.styles.theme import COLORS, TYPOGRAPHY, SIZING, SPACING, SHADOWS

# Google Fonts imports for enhanced typography
GOOGLE_FONTS = [
    "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap",
    "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap"
]

# Enhanced global styles for premium dashboard
styles = {
    # Enhanced global styles with Google Fonts
    "body": {
        "background": f"linear-gradient(135deg, {COLORS['background']} 0%, {COLORS['surface']} 100%)",
        "color": COLORS["text"],
        "font_family": TYPOGRAPHY["font_family"],
        "margin": "0",
        "padding": "0",
        "line_height": TYPOGRAPHY["line_heights"]["normal"],
        "font_feature_settings": "'kern', 'liga', 'clig', 'calt'",
        "text_rendering": "optimizeLegibility",
        "-webkit_font_smoothing": "antialiased",
        "-moz_osx_font_smoothing": "grayscale",
    },
    
    # Enhanced component styles
    rx.input: {
        "background": COLORS["white"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "font_family": TYPOGRAPHY["font_family"],
        "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "box_shadow": SHADOWS["sm"],
        "_focus": {
            "border_color": COLORS["primary"],
            "box_shadow": SHADOWS["card_focus"],
            "outline": "none",
            "transform": "translateY(-1px)",
        },
        "_hover": {
            "border_color": COLORS["primary_light"],
            "box_shadow": SHADOWS["card"],
        },
    },
    
    rx.button: {
        "background": f"linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_hover']} 100%)",
        "color": COLORS["white"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "font_family": TYPOGRAPHY["font_family"],
        "border": "none",
        "cursor": "pointer",
        "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "box_shadow": SHADOWS["button"],
        "_hover": {
            "background": f"linear-gradient(135deg, {COLORS['primary_hover']} 0%, {COLORS['primary']} 100%)",
            "transform": "translateY(-2px)",
            "box_shadow": SHADOWS["primary"],
        },
        "_active": {
            "transform": "translateY(0px)",
            "box_shadow": SHADOWS["sm"],
        },
    },
    
    rx.link: {
        "color": COLORS["primary"],
        "text_decoration": "none",
        "font_weight": TYPOGRAPHY["font_weights"]["medium"],
        "font_family": TYPOGRAPHY["font_family"],
        "transition": "all 0.3s ease",
        "position": "relative",
        "_hover": {
            "color": COLORS["primary_hover"],
            "transform": "translateY(-1px)",
        },
        "_after": {
            "content": "''",
            "position": "absolute",
            "width": "0",
            "height": "2px",
            "bottom": "-2px",
            "left": "0",
            "background": COLORS["primary"],
            "transition": "width 0.3s ease",
        },
        "_hover:after": {
            "width": "100%",
        },
    },
    
    rx.heading: {
        "color": COLORS["text"],
        "font_weight": TYPOGRAPHY["font_weights"]["bold"],
        "font_family": TYPOGRAPHY["font_family_display"],
        "line_height": TYPOGRAPHY["line_heights"]["tight"],
        "letter_spacing": TYPOGRAPHY["letter_spacing"]["tight"],
        "margin": "0",
    },
    
    rx.text: {
        "color": COLORS["text"],
        "font_family": TYPOGRAPHY["font_family"],
        "line_height": TYPOGRAPHY["line_heights"]["relaxed"],
        "margin": "0",
    },
}

# Enhanced button variants with premium styling
button_variants = {
    "primary": {
        "background": f"linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_hover']} 100%)",
        "color": COLORS["white"],
        "border": "none",
        "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "box_shadow": SHADOWS["button"],
        "_hover": {
            "background": f"linear-gradient(135deg, {COLORS['primary_hover']} 0%, {COLORS['primary']} 100%)",
            "transform": "translateY(-2px)",
            "box_shadow": SHADOWS["primary"],
        },
        "_active": {
            "transform": "translateY(0px)",
            "box_shadow": SHADOWS["sm"],
        },
    },
    "secondary": {
        "background": COLORS["white"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "color": COLORS["text"],
        "font_weight": TYPOGRAPHY["font_weights"]["medium"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "transition": "all 0.3s ease",
        "box_shadow": SHADOWS["button"],
        "_hover": {
            "background": COLORS["surface"],
            "border_color": COLORS["primary_light"],
            "color": COLORS["primary"],
            "transform": "translateY(-1px)",
            "box_shadow": SHADOWS["button_hover"],
        },
    },
    "ghost": {
        "background": "transparent",
        "border": "none",
        "color": COLORS["text_muted"],
        "font_weight": TYPOGRAPHY["font_weights"]["medium"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "transition": "all 0.3s ease",
        "_hover": {
            "background": COLORS["surface_hover"],
            "color": COLORS["text"],
            "transform": "translateY(-1px)",
        },
    },
    "danger": {
        "background": f"linear-gradient(135deg, {COLORS['error']} 0%, #dc2626 100%)",
        "color": COLORS["white"],
        "border": "none",
        "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "transition": "all 0.3s ease",
        "box_shadow": SHADOWS["button"],
        "_hover": {
            "background": f"linear-gradient(135deg, #dc2626 0%, {COLORS['error']} 100%)",
            "transform": "translateY(-2px)",
            "box_shadow": SHADOWS["error"],
        },
    },
    "success": {
        "background": f"linear-gradient(135deg, {COLORS['success']} 0%, #047857 100%)",
        "color": COLORS["white"],
        "border": "none",
        "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
        "border_radius": SIZING["border_radius"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "transition": "all 0.3s ease",
        "box_shadow": SHADOWS["button"],
        "_hover": {
            "background": f"linear-gradient(135deg, #047857 0%, {COLORS['success']} 100%)",
            "transform": "translateY(-2px)",
            "box_shadow": SHADOWS["success"],
        },
    },
}

# Enhanced card variants for premium dashboard content
card_variants = {
    "default": {
        "background": COLORS["white"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius_lg"],
        "padding": SPACING["lg"],
        "box_shadow": SHADOWS["card"],
        "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "_hover": {
            "box_shadow": SHADOWS["card_hover"],
            "transform": "translateY(-2px)",
            "border_color": COLORS["border_accent"],
        },
    },
    "feature": {
        "background": "linear-gradient(145deg, #ffffff 0%, #fafbfc 100%)",
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius_lg"],
        "padding": SPACING["lg"],
        "box_shadow": SHADOWS["card"],
        "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "cursor": "pointer",
        "min_height": SIZING["card_min_height"],
        "position": "relative",
        "overflow": "hidden",
        "_hover": {
            "box_shadow": SHADOWS["card_hover"],
            "transform": "translateY(-4px) scale(1.02)",
            "border_color": COLORS["primary_light"],
            "background": "linear-gradient(145deg, #ffffff 0%, #f8fafc 100%)",
        },
        "_active": {
            "transform": "translateY(-2px) scale(1.01)",
        },
    },
    "metric": {
        "background": "linear-gradient(135deg, #ffffff 0%, #f9fafb 100%)",
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius_lg"],
        "padding": SPACING["lg"],
        "box_shadow": SHADOWS["card"],
        "text_align": "center",
        "min_height": "120px",
        "transition": "all 0.3s ease",
        "_hover": {
            "transform": "translateY(-2px)",
            "box_shadow": SHADOWS["card_hover"],
        },
    },
    "elevated": {
        "background": "linear-gradient(145deg, #ffffff 0%, #fafbfc 100%)",
        "border": f"{SIZING['border_width']} solid {COLORS['border_light']}",
        "border_radius": SIZING["border_radius_xl"],
        "padding": SPACING["xl"],
        "box_shadow": SHADOWS["lg"],
        "backdrop_filter": "blur(8px)",
    },
    "glass": {
        "background": "rgba(255, 255, 255, 0.8)",
        "border": f"{SIZING['border_width']} solid rgba(255, 255, 255, 0.2)",
        "border_radius": SIZING["border_radius_lg"],
        "padding": SPACING["lg"],
        "backdrop_filter": "blur(12px)",
        "box_shadow": "0 8px 32px 0 rgba(31, 38, 135, 0.37)",
        "transition": "all 0.3s ease",
        "_hover": {
            "background": "rgba(255, 255, 255, 0.9)",
            "transform": "translateY(-2px)",
        },
    },
}

# Sidebar navigation styles
sidebar_variants = {
    "container": {
        "background": COLORS["sidebar"],
        "border_right": f"{SIZING['border_width']} solid {COLORS['border']}",
        "width": SIZING["sidebar_width"],
        "height": SIZING["full_height"],
        "padding": SPACING["lg"],
        "position": "fixed",
        "left": "0",
        "top": "0",
        "overflow_y": "auto",
    },
    "section": {
        "margin_bottom": SPACING["lg"],
    },
    "section_title": {
        "font_size": TYPOGRAPHY["font_sizes"]["xs"],
        "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
        "color": COLORS["text_muted"],
        "text_transform": "uppercase",
        "letter_spacing": "0.05em",
        "margin_bottom": SPACING["sm"],
    },
    "nav_item": {
        "display": "flex",
        "align_items": "center",
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text_muted"],
        "text_decoration": "none",
        "font_weight": TYPOGRAPHY["font_weights"]["medium"],
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "margin_bottom": SPACING["xs"],
        "transition": "all 0.2s ease",
        "_hover": {
            "background_color": COLORS["surface_hover"],
            "color": COLORS["text"],
        },
    },
    "nav_item_active": {
        "display": "flex",
        "align_items": "center",
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "border_radius": SIZING["border_radius"],
        "background_color": COLORS["primary"],
        "color": COLORS["white"],
        "text_decoration": "none",
        "font_weight": TYPOGRAPHY["font_weights"]["semibold"],
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "margin_bottom": SPACING["xs"],
    },
}

# Header styles
header_variants = {
    "container": {
        "background": COLORS["white"],
        "border_bottom": f"{SIZING['border_width']} solid {COLORS['border']}",
        "height": SIZING["header_height"],
        "padding": f"0 {SPACING['lg']}",
        "display": "flex",
        "align_items": "center",
        "justify_content": "space-between",
        "position": "fixed",
        "top": "0",
        "left": SIZING["sidebar_width"],
        "right": "0",
        "z_index": "10",
    },
    "search": {
        "background": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius_lg"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "width": "400px",
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "_focus": {
            "border_color": COLORS["primary"],
            "box_shadow": f"0 0 0 3px {COLORS['primary']}20",
        },
    },
    "user_profile": {
        "display": "flex",
        "align_items": "center",
        "gap": SPACING["sm"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "border_radius": SIZING["border_radius"],
        "transition": "all 0.2s ease",
        "_hover": {
            "background_color": COLORS["surface"],
        },
    },
}

# Main content area styles
content_variants = {
    "container": {
        "margin_left": SIZING["sidebar_width"],
        "margin_top": SIZING["header_height"],
        "padding": SPACING["lg"],
        "min_height": SIZING["content_height"],
        "background": COLORS["surface"],
    },
    "page_header": {
        "margin_bottom": SPACING["xl"],
    },
    "page_title": {
        "font_size": TYPOGRAPHY["font_sizes"]["3xl"],
        "font_weight": TYPOGRAPHY["font_weights"]["bold"],
        "color": COLORS["text"],
        "margin_bottom": SPACING["sm"],
    },
    "page_subtitle": {
        "font_size": TYPOGRAPHY["font_sizes"]["lg"],
        "color": COLORS["text_muted"],
        "font_weight": TYPOGRAPHY["font_weights"]["normal"],
    },
}

# Grid system for dashboard layout
grid_variants = {
    "feature_grid": {
        "display": "grid",
        "grid_template_columns": "repeat(auto-fit, minmax(300px, 1fr))",
        "gap": SPACING["lg"],
        "margin_bottom": SPACING["xl"],
    },
    "metric_grid": {
        "display": "grid",
        "grid_template_columns": "repeat(auto-fit, minmax(200px, 1fr))",
        "gap": SPACING["md"],
        "margin_bottom": SPACING["xl"],
    },
    "two_column": {
        "display": "grid",
        "grid_template_columns": "1fr 1fr",
        "gap": SPACING["lg"],
    },
    "three_column": {
        "display": "grid",
        "grid_template_columns": "1fr 1fr 1fr",
        "gap": SPACING["lg"],
    },
}

# Input variants for forms
input_variants = {
    "default": {
        "background_color": COLORS["white"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "width": "100%",
        "_focus": {
            "border_color": COLORS["primary"],
            "box_shadow": f"0 0 0 3px {COLORS['primary']}20",
            "outline": "none",
        },
        "_hover": {"border_color": COLORS["primary"]},
    },
    "error": {
        "background_color": COLORS["white"],
        "border": f"{SIZING['border_width']} solid {COLORS['error']}",
        "border_radius": SIZING["border_radius"],
        "color": COLORS["text"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "width": "100%",
        "_focus": {
            "border_color": COLORS["error"],
            "box_shadow": f"0 0 0 3px {COLORS['error']}20",
            "outline": "none",
        },
    },
    "search": {
        "background_color": COLORS["surface"],
        "border": f"{SIZING['border_width']} solid {COLORS['border']}",
        "border_radius": SIZING["border_radius_lg"],
        "color": COLORS["text"],
        "padding": f"{SPACING['sm']} {SPACING['md']}",
        "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        "_focus": {
            "border_color": COLORS["primary"],
            "box_shadow": f"0 0 0 3px {COLORS['primary']}20",
            "outline": "none",
        },
        "_placeholder": {
            "color": COLORS["text_light"],
        },
    },
}

# Utility classes
utilities = {
    "shadow_sm": {"box_shadow": SHADOWS["sm"]},
    "shadow_md": {"box_shadow": SHADOWS["md"]},
    "shadow_lg": {"box_shadow": SHADOWS["lg"]},
    "shadow_xl": {"box_shadow": SHADOWS["xl"]},
    "rounded": {"border_radius": SIZING["border_radius"]},
    "rounded_lg": {"border_radius": SIZING["border_radius_lg"]},
    "rounded_xl": {"border_radius": SIZING["border_radius_xl"]},
    "transition": {"transition": "all 0.2s ease"},
    "cursor_pointer": {"cursor": "pointer"},
} 