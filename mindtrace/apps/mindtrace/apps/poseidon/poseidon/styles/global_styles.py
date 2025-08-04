"""
Global Styling Variables for Poseidon

This module contains all global styling variables, colors, typography,
spacing, and component variants.
"""

# Color Palette
COLORS = {
    # Primary brand colors
    "primary": "#0057FF",           # Main blue from logo and buttons
    "primary_dark": "#0041CC",      # Darker blue for hover states
    "primary_light": "#0066FF",     # Lighter blue for gradients
    
    # Secondary colors
    "secondary": "#DC2626",         # Red for danger/super admin
    "secondary_dark": "#B91C1C",    # Darker red for hover states
    
    # Text colors
    "text_primary": "rgb(15, 23, 42)",    # Dark text for headings
    "text_secondary": "rgb(100, 116, 139)", # Muted text for subtitles
    "text_muted": "rgba(100, 116, 139, 0.6)", # Placeholder text
    
    # Background colors
    "background_primary": "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f1f5f9 100%)",
    "background_card": "rgba(255, 255, 255, 0.95)",
    "background_input": "rgba(248, 250, 252, 0.8)",
    "background_input_focus": "rgba(255, 255, 255, 0.95)",
    
    # Border colors
    "border_primary": "rgba(226, 232, 240, 0.6)",
    "border_focus": "#0057FF",
    "border_card": "rgba(255, 255, 255, 0.2)",
    "border_divider": "rgba(226, 232, 240, 0.5)",
    
    # Status colors
    "success": "#10B981",
    "error": "#EF4444",
    "warning": "#F59E0B",
    "info": "#3B82F6",
    
    # Utility colors
    "white": "#FFFFFF",
    "transparent": "transparent",
}

# Typography System
TYPOGRAPHY = {
    "font_family": '"Inter", system-ui, sans-serif',
    "font_sizes": {
        "xs": "0.75rem",
        "sm": "0.875rem",
        "base": "1rem",
        "lg": "1.125rem",
        "xl": "1.25rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem",
        "5xl": "2.5rem",
    },
    "font_weights": {
        "light": "300",
        "normal": "400",
        "medium": "500",
        "semibold": "600",
        "bold": "700",
        "extrabold": "800",
    },
    "line_heights": {
        "tight": "1.0",
        "normal": "1.1",
        "relaxed": "1.4",
        "loose": "1.5",
    },
    "letter_spacing": {
        "tight": "-0.025em",
        "normal": "-0.02em",
        "wide": "0.15em",
    },
}

# Spacing System
SPACING = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2rem",
    "2xl": "3rem",
    "3xl": "4rem",
}

# Sizing System
SIZING = {
    "border_radius": {
        "sm": "8px",
        "md": "12px",
        "lg": "16px",
        "xl": "24px",
    },
    "max_width": "1200px",
    "container_padding": "0 2rem",
}

# Shadows and Effects
EFFECTS = {
    "shadows": {
        "sm": "0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)",
        "md": "0 4px 6px rgba(0, 0, 0, 0.1), 0 1px 3px rgba(0, 0, 0, 0.08)",
        "lg": "0 8px 32px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.04)",
        "xl": "0 4px 16px rgba(0, 87, 255, 0.3)",
        "danger": "0 4px 16px rgba(220, 38, 38, 0.3)",
    },
    "transitions": {
        "fast": "all 0.2s ease-in-out",
        "normal": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "slow": "all 0.6s ease-out",
    },
    "backdrop_filter": "blur(20px)",
    "backdrop_filter_light": "blur(10px)",
}

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
            "background": f"linear-gradient(135deg, {COLORS['secondary']} 0%, {COLORS['secondary_dark']} 100%)",
            "hover_background": f"linear-gradient(135deg, {COLORS['secondary_dark']} 0%, #991B1B 100%)",
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

# Animation Keyframes
ANIMATIONS = {
    "float": """
        @keyframes float {
            0%, 100% { transform: translateY(0px) rotate(0deg); }
            50% { transform: translateY(-15px) rotate(2deg); }
        }
    """,
    "shimmer": """
        @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
    """,
    "fadeInUp": """
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    """,
    "slideInUp": """
        @keyframes slideInUp {
            from {
                opacity: 0;
                transform: translateY(30px) scale(0.98);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }
    """,
    "fadeIn": """
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
    """,
    "shake": """
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-3px); }
            75% { transform: translateX(3px); }
        }
    """,
}

# Size variants for components
SIZE_VARIANTS = {
    "input": {
        "small": {
            "padding": "0.5rem 0.75rem",
            "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        },
        "medium": {
            "padding": "0.65rem 0.9rem",
            "font_size": "0.9rem",
        },
        "large": {
            "padding": "0.75rem 1rem",
            "font_size": "0.925rem",
        }
    },
    "button": {
        "small": {
            "padding": "0.5rem 1rem",
            "font_size": TYPOGRAPHY["font_sizes"]["sm"],
        },
        "medium": {
            "padding": "0.65rem 1.25rem",
            "font_size": "0.9rem",
        },
        "large": {
            "padding": "0.75rem 1.5rem",
            "font_size": "0.925rem",
        },
    },
} 