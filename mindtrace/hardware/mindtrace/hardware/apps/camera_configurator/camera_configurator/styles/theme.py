"""Theme and styling configuration for camera configurator."""

import reflex as rx

# Color palette
colors = {
    # Primary colors
    "primary": "#2563eb",
    "primary_light": "#60a5fa", 
    "primary_dark": "#1e40af",
    
    # Secondary colors
    "secondary": "#64748b",
    "secondary_light": "#94a3b8",
    "secondary_dark": "#475569",
    
    # Status colors
    "success": "#059669",
    "success_light": "#10b981",
    "warning": "#d97706",
    "warning_light": "#f59e0b",
    "error": "#dc2626",
    "error_light": "#ef4444",
    "info": "#0284c7",
    "info_light": "#0ea5e9",
    
    # Neutral colors
    "white": "#ffffff",
    "gray_50": "#f9fafb",
    "gray_100": "#f3f4f6",
    "gray_200": "#e5e7eb",
    "gray_300": "#d1d5db",
    "gray_400": "#9ca3af",
    "gray_500": "#6b7280",
    "gray_600": "#4b5563",
    "gray_700": "#374151",
    "gray_800": "#1f2937",
    "gray_900": "#111827",
    
    # Surface colors
    "background": "#ffffff",
    "surface": "#f9fafb",
    "surface_2": "#f3f4f6",
    "border": "#e5e7eb",
    "border_light": "#f3f4f6",
}

# Spacing (using Reflex theme scale)
spacing = {
    "xs": "1",   # smallest
    "sm": "2",   # small
    "md": "3",   # medium
    "lg": "4",   # large
    "xl": "5",   # extra large
    "2xl": "6",  # 2x extra large
    "3xl": "7",  # 3x extra large
}

# CSS spacing values for direct styling (similar to Poseidon approach)
css_spacing = {
    "xs": "0.25rem",  # 4px
    "sm": "0.5rem",   # 8px
    "md": "1rem",     # 16px
    "lg": "1.5rem",   # 24px
    "xl": "2rem",     # 32px
    "2xl": "3rem",    # 48px
    "3xl": "4rem",    # 64px
}

# Layout spacing values for consistent content spacing
layout = {
    "content_gap": "1.5rem",    # 24px - gap between major sections
    "content_padding": "2rem",  # 32px - main content padding
    "section_gap": "2rem",      # 32px - gap between page sections 
    "container_max_width": "1200px",  # max content width
}

# Border radius
radius = {
    "sm": "0.25rem",  # 4px
    "md": "0.5rem",   # 8px
    "lg": "0.75rem",  # 12px
    "xl": "1rem",     # 16px
    "full": "9999px", # fully rounded
}

# Shadows
shadows = {
    "sm": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    "md": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
    "lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    "xl": "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
}

# Reflex theme configuration
theme_config = rx.theme(
    appearance="light",
    has_background=True,
    radius="medium",
    accent_color="blue",
)

# Card variants
card_variants = {
    "base": {
        "background": colors["white"],
        "border": f"1px solid {colors['border']}",
        "border_radius": radius["lg"],
        "box_shadow": shadows["sm"],
        "padding": css_spacing["lg"],
    },
    "elevated": {
        "background": colors["white"],
        "border": f"1px solid {colors['border']}",
        "border_radius": radius["lg"],
        "box_shadow": shadows["md"],
        "padding": spacing["lg"],
    },
    "camera": {
        "background": colors["white"],
        "border": f"1px solid {colors['border']}",
        "border_radius": radius["lg"],
        "box_shadow": shadows["sm"],
        "padding": css_spacing["lg"],
        "transition": "all 0.2s ease",
        "_hover": {
            "box_shadow": shadows["md"],
            "transform": "translateY(-2px)",
        }
    }
}

# Button variants
button_variants = {
    "primary": {
        "background": colors["primary"],
        "color": colors["white"],
        "border": "none",
        "border_radius": radius["md"],
        "padding": f"{css_spacing['sm']} {css_spacing['md']}",
        "_hover": {
            "background": colors["primary_dark"],
        }
    },
    "secondary": {
        "background": colors["gray_100"],
        "color": colors["gray_700"],
        "border": f"1px solid {colors['border']}",
        "border_radius": radius["md"],
        "padding": f"{css_spacing['sm']} {css_spacing['md']}",
        "_hover": {
            "background": colors["gray_200"],
        }
    },
    "success": {
        "background": colors["success"],
        "color": colors["white"],
        "border": "none",
        "border_radius": radius["md"],
        "padding": f"{css_spacing['sm']} {css_spacing['md']}",
        "_hover": {
            "background": colors["success_light"],
        }
    },
    "error": {
        "background": colors["error"],
        "color": colors["white"],
        "border": "none",
        "border_radius": radius["md"],
        "padding": f"{css_spacing['sm']} {css_spacing['md']}",
        "_hover": {
            "background": colors["error_light"],
        }
    }
}

# Status badge styles
status_badges = {
    "initialized": {
        "background": colors["success"],
        "color": colors["white"],
        "text": "●  Initialized"
    },
    "available": {
        "background": colors["warning"],
        "color": colors["white"], 
        "text": "●  Available"
    },
    "busy": {
        "background": colors["info"],
        "color": colors["white"],
        "text": "●  Busy"
    },
    "error": {
        "background": colors["error"],
        "color": colors["white"],
        "text": "●  Error"
    },
    "unknown": {
        "background": colors["gray_400"],
        "color": colors["white"],
        "text": "●  Unknown"
    }
}