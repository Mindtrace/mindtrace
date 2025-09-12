"""
Metric Card Component

A reusable card component for displaying key metrics with title, value, and optional subtitle.
"""

import reflex as rx
from typing import Optional
from poseidon.styles.global_styles import THEME as T


def metric_card(title: str, value: str, subtitle: Optional[str] = None, loading: bool = False, empty: bool = False, empty_message: str = "No data") -> rx.Component:
    """Create a metric card for displaying key metrics."""

    loading_overlay = rx.box(
        rx.center(
            rx.spinner(size="2"),
            width="100%",
            height="100%",
        ),
        style={
            "position": "absolute",
            "top": 0,
            "left": 0,
            "right": 0,
            "bottom": 0,
            "display": "flex",
            "align_items": "center",
            "justify_content": "center",
            "background_color": "rgba(0,0,0,0.05)",
            "backdrop_filter": T.effects.backdrop_filter_light,
            "z_index": 5,
        },
    )

    empty_overlay = rx.box(
        rx.center(
            rx.hstack(
                rx.icon("circle-off", size=14),
                rx.text(empty_message, color=T.colors.fg_muted, font_size=T.typography.fs_sm),
                spacing="2",
                align="center",
            ),
            width="100%",
            height="100%",
        ),
        style={
            "position": "absolute",
            "top": 0,
            "left": 0,
            "right": 0,
            "bottom": 0,
            "display": "flex",
            "align_items": "center",
            "justify_content": "center",
            "background_color": "rgba(0,0,0,0.03)",
            "backdrop_filter": T.effects.backdrop_filter_light,
            "z_index": 4,
        },
    )

    overlay = rx.cond(
        loading,
        loading_overlay,
        rx.cond(empty, empty_overlay, None),
    )

    return rx.card(
        rx.vstack(
            rx.text(
                title,
                font_size=T.typography.fs_sm,
                color=T.colors.fg_muted,
                font_weight=T.typography.fw_500,
            ),
            rx.text(
                value,
                font_size=T.typography.fs_3xl,
                font_weight=T.typography.fw_700,
                color=T.colors.fg,
            ),
            rx.cond(
                subtitle,
                rx.text(
                    subtitle,
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_subtle,
                ),
                rx.fragment(),
            ),
            spacing="2",
            align="start",
        ),
        overlay,
        padding=T.spacing.space_4,
        background=T.colors.surface,
        border=f"1px solid {T.colors.border}",
        border_radius=T.radius.r_lg,
        box_shadow=T.shadows.shadow_1,
        width="100%",
        style={
            "position": "relative",
            "overflow": "hidden",
        },
    )