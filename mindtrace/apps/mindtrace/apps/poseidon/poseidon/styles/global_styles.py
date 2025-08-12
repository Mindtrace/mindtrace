"""
Global Styling Variables for Poseidon

This module contains all global styling variables, colors, typography,
spacing, and component variants.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorTokens:
    accent: str
    accent_fg: str
    ring: str
    bg: str
    surface: str
    surface_2: str
    border: str
    fg: str
    fg_muted: str
    fg_subtle: str
    success: str
    warning: str
    danger: str
    info: str


@dataclass(frozen=True)
class TypographyTokens:
    font_sans: str
    fw_400: str
    fw_500: str
    fw_600: str
    fw_700: str
    fs_xs: str
    fs_sm: str
    fs_base: str
    fs_lg: str
    fs_xl: str
    fs_2xl: str
    fs_3xl: str
    fs_4xl: str
    fs_5xl: str


@dataclass(frozen=True)
class SpacingTokens:
    space_1: str
    space_2: str
    space_3: str
    space_4: str
    space_5: str
    space_6: str
    space_8: str
    space_10: str


@dataclass(frozen=True)
class RadiusTokens:
    r_sm: str
    r_md: str
    r_lg: str
    r_xl: str
    r_full: str


@dataclass(frozen=True)
class ShadowTokens:
    shadow_1: str
    shadow_2: str


@dataclass(frozen=True)
class MotionTokens:
    ease: str
    dur_fast: str
    dur: str
    dur_slow: str


@dataclass(frozen=True)
class LayoutTokens:
    sidebar_w: str
    sidebar_w_collapsed: str
    header_h: str
    content_pad: str
    content_gap: str


@dataclass(frozen=True)
class ZTokens:
    z_header: int
    z_overlay: int


@dataclass(frozen=True)
class ThemeTokens:
    colors: ColorTokens
    typography: TypographyTokens
    spacing: SpacingTokens
    radius: RadiusTokens
    shadows: ShadowTokens
    motion: MotionTokens
    layout: LayoutTokens
    z: ZTokens

    def __getattr__(self, name: str):
        for group in (
            self.colors,
            self.typography,
            self.spacing,
            self.radius,
            self.shadows,
            self.motion,
            self.layout,
            self.z,
        ):
            if hasattr(group, name):
                return getattr(group, name)
        raise AttributeError(name)


THEME = ThemeTokens(
    colors=ColorTokens(
        accent="#0057FF",
        accent_fg="#ffffff",
        ring="rgba(0,87,255,.35)",
        bg="#F9F9F9",
        surface="#ffffff",
        surface_2="#fbfdff",
        border="#e2e8f0",
        fg="#0f172a",
        fg_muted="#64748b",
        fg_subtle="rgba(100,116,139,.6)",
        success="#10B981",
        warning="#F59E0B",
        danger="#EF4444",
        info="#3B82F6",
    ),
    typography=TypographyTokens(
        font_sans="Inter, system-ui, sans-serif",
        fw_400="400",
        fw_500="500",
        fw_600="600",
        fw_700="700",
        fs_xs=".75rem",
        fs_sm=".875rem",
        fs_base="1rem",
        fs_lg="1.125rem",
        fs_xl="1.25rem",
        fs_2xl="1.5rem",
        fs_3xl="1.875rem",
        fs_4xl="2.25rem",
        fs_5xl="2.5rem",
    ),
    spacing=SpacingTokens(
        space_1=".25rem",
        space_2=".5rem",
        space_3=".75rem",
        space_4="1rem",
        space_5="1.25rem",
        space_6="1.5rem",
        space_8="2rem",
        space_10="2.5rem",
    ),
    radius=RadiusTokens(
        r_sm="6px",
        r_md="10px",
        r_lg="14px",
        r_xl="20px",
        r_full="999px",
    ),
    shadows=ShadowTokens(
        shadow_1="0 1px 2px rgba(15,23,42,.06)",
        shadow_2="0 2px 10px rgba(15,23,42,.08)",
    ),
    motion=MotionTokens(
        ease="cubic-bezier(.4,0,.2,1)",
        dur_fast=".15s",
        dur=".25s",
        dur_slow=".4s",
    ),
    layout=LayoutTokens(
        sidebar_w="260px",
        sidebar_w_collapsed="72px",
        header_h="60px",
        content_pad="24px",  
        content_gap="24px",
    ),
    z=ZTokens(
        z_header=10,
        z_overlay=1000,
    ),
)

# Shorthands for DX
T = THEME
C = THEME.colors
SP = THEME.spacing
R = THEME.radius
L = THEME.layout
Z = THEME.z
Ty = THEME.typography

# Color Palette
COLORS = {
    # Primary brand colors
    "primary": "#0057FF",           # Main blue from logo and buttons
    "primary_dark": "#0041CC",      # Darker blue for hover states
    "primary_light": "#0066FF",     # Lighter blue for gradients
    
    # Secondary colors
    "secondary": "#0EA5E9",         # Sky blue - complements royal blue
    "secondary_dark": "#0284C7",    # Darker sky blue for hover states
    
    # Danger colors
    "danger": "#DC2626",            # Red for danger
    "danger_dark": "#B91C1C",       # Darker red for hover states
    
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