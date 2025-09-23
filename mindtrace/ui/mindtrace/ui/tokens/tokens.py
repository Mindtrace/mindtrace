"""
Mindtrace UI — Tokens

Owns:
- Token dataclasses
- THEME instance (all raw values)
- Shorthands (T, C, SP, R, L, Z, SH, M, FX, AN, Ty)

No component variants here.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------- Token dataclasses ----------

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
    lh_normal: str
    lh_loose: str
    ls_tight: str
    ls_normal: str
    ls_wide: str


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
class EffectsTokens:
    backdrop_filter: str
    backdrop_filter_light: str


@dataclass(frozen=True)
class AnimationTokens:
    float: str
    shimmer: str
    fadeInUp: str
    slideInUp: str
    fadeIn: str
    shake: str


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
    effects: EffectsTokens
    animations: AnimationTokens
    layout: LayoutTokens
    z: ZTokens

    # ergonomic passthrough: T.fs_sm, T.accent, etc.
    def __getattr__(self, name: str):
        for group in (
            self.colors, self.typography, self.spacing, self.radius, self.shadows,
            self.motion, self.effects, self.animations, self.layout, self.z,
        ):
            if hasattr(group, name):
                return getattr(group, name)
        raise AttributeError(name)


# ---------- THEME (token values) ----------

THEME = ThemeTokens(
    colors=ColorTokens(
        accent="#0057FF",
        accent_fg="#ffffff",
        ring="rgba(0,87,255,0.12)",
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
        lh_normal="1.1",
        lh_loose="1.5",
        ls_tight="-0.025em",
        ls_normal="-0.02em",
        ls_wide="0.15em",
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
    effects=EffectsTokens(
        backdrop_filter="blur(20px)",
        backdrop_filter_light="blur(10px)",
    ),
    animations=AnimationTokens(
        float="""
            @keyframes float {
                0%, 100% { transform: translateY(0px) rotate(0deg); }
                50% { transform: translateY(-15px) rotate(2deg); }
            }
        """,
        shimmer="""
            @keyframes shimmer {
                0% { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }
        """,
        fadeInUp="""
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }
        """,
        slideInUp="""
            @keyframes slideInUp {
                from { opacity: 0; transform: translateY(30px) scale(0.98); }
                to { opacity: 1; transform: translateY(0) scale(1); }
            }
        """,
        fadeIn="""
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        """,
        shake="""
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-3px); }
                75% { transform: translateX(3px); }
            }
        """,
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

# Shorthands
T = THEME
C = THEME.colors
SP = THEME.spacing
R = THEME.radius
L = THEME.layout
Z = THEME.z
SH = THEME.shadows
M = THEME.motion
FX = THEME.effects
AN = THEME.animations
Ty = THEME.typography


__all__ = [
    # instances
    "THEME", "T", "C", "SP", "R", "L", "Z", "SH", "M", "FX", "AN", "Ty",
    # dataclasses
    "ThemeTokens", "ColorTokens", "TypographyTokens", "SpacingTokens", "RadiusTokens",
    "ShadowTokens", "MotionTokens", "EffectsTokens", "AnimationTokens",
    "LayoutTokens", "ZTokens",
]
