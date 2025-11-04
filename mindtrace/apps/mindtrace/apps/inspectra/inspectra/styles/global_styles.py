from dataclasses import dataclass
from typing import Literal

import reflex as rx

# ───────────────────────────────────────────────
# 🎨 COLOR TOKENS
# ───────────────────────────────────────────────

ColorRole = Literal[
    "brand",
    "brand_light",
    "surface",
    "background",
    "border",
    "text_primary",
    "text_secondary",
    "error",
]


@dataclass(frozen=True)
class ColorTokens:
    """Semantic color palette."""

    brand: str = "#184937"  # Inspectra green
    brand_light: str = "#60CCA5"
    surface: str = "#ffffff"
    background: str = "#f9fafb"
    border: str = "rgba(0,0,0,0.1)"
    text_primary: str = "#0f172a"
    text_secondary: str = "#475569"
    error: str = "#dc2626"


# ───────────────────────────────────────────────
# 📏 SPACING + LAYOUT TOKENS
# ───────────────────────────────────────────────

SpaceSize = Literal["xs", "sm", "md", "lg", "xl", "2xl"]


@dataclass(frozen=True)
class SpacingTokens:
    """Semantic spacing scale."""

    xs: str = "4px"
    sm: str = "8px"
    md: str = "16px"
    lg: str = "24px"
    xl: str = "32px"
    _2xl: str = "40px"  # double underscore since identifiers can’t start with numbers


@dataclass(frozen=True)
class RadiusTokens:
    """Border radius scale."""

    sm: str = "6px"
    md: str = "12px"
    lg: str = "20px"


@dataclass(frozen=True)
class ZIndexTokens:
    header: int = 100
    overlay: int = 1000


# ───────────────────────────────────────────────
# ✍️ TYPOGRAPHY TOKENS
# ───────────────────────────────────────────────


@dataclass(frozen=True)
class TypographyTokens:
    """Font families, sizes, weights."""

    font_family: str = "Inter, system-ui, sans-serif"
    size_sm: str = "14px"
    size_md: str = "16px"
    size_lg: str = "20px"
    weight_regular: str = "400"
    weight_medium: str = "500"
    weight_bold: str = "700"


# ───────────────────────────────────────────────
# 🧱 LAYOUT TOKENS
# ───────────────────────────────────────────────


@dataclass(frozen=True)
class LayoutTokens:
    header_h: str = "72px"
    sidebar_w: str = "120px"


# ───────────────────────────────────────────────
# 🎯 DESIGN SYSTEM ROOT
# ───────────────────────────────────────────────


@dataclass(frozen=True)
class DesignSystem:
    """Single source of truth for design tokens."""

    color: ColorTokens = ColorTokens()
    space: SpacingTokens = SpacingTokens()
    radius: RadiusTokens = RadiusTokens()
    text: TypographyTokens = TypographyTokens()
    layout: LayoutTokens = LayoutTokens()
    z: ZIndexTokens = ZIndexTokens()


DS = DesignSystem()  # Shorthand alias


# ───────────────────────────────────────────────
# 💅 GLOBAL CSS INJECTION
# ───────────────────────────────────────────────


def global_css() -> rx.Component:
    """Inject global CSS variables for Inspectra theme."""
    c, s, r, t, layout = DS.color, DS.space, DS.radius, DS.text, DS.layout

    return rx.html(f"""
    <style>
        :root {{
            --color-brand: {c.brand};
            --color-brand-light: {c.brand_light};
            --color-surface: {c.surface};
            --color-background: {c.background};
            --color-border: {c.border};
            --text-primary: {c.text_primary};
            --text-secondary: {c.text_secondary};

            --font-family: {t.font_family};

            --space-xs: {s.xs};
            --space-sm: {s.sm};
            --space-md: {s.md};
            --space-lg: {s.lg};
            --space-xl: {s.xl};

            --radius-sm: {r.sm};
            --radius-md: {r.md};
            --radius-lg: {r.lg};

            --header-h: {layout.header_h};
            --sidebar-w: {layout.sidebar_w};
        }}
    </style>
    """)
