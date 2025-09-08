"""
Metric Card Component

A reusable card component for displaying key metrics with title, value, and optional subtitle.
"""

import reflex as rx
from typing import Optional
from poseidon.styles.global_styles import THEME as T


def metric_card(title: str, value: str, subtitle: Optional[str] = None) -> rx.Component:
    """Create a metric card for displaying key metrics."""
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
        padding=T.spacing.space_4,
        background=T.colors.surface,
        border=f"1px solid {T.colors.border}",
        border_radius=T.radius.r_lg,
        box_shadow=T.shadows.shadow_1,
        width="100%",
    )