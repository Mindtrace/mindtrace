"""
Metric Card Component

A reusable card component for displaying key metrics with title, value, and optional subtitle.
Exact layout & styles aligned to provided CSS spec.
"""

import reflex as rx
from typing import Optional
from poseidon.styles.global_styles import THEME as T


def metric_card(
    title: str,
    value: str,
    subtitle: Optional[str] = None,
    *,
    loading: bool = False,
    empty: bool = False,
    empty_message: str = "No data",
    # New optional visual props to match the spec:
    icon: str = "bar-chart-3",          # 24x24 visual
    accent: str = "#5BB98B",            # icon / accent color
    delta: Optional[str] = None,        # e.g. "+3.4%"
    delta_note: Optional[str] = None,   # e.g. "since last week"
    width: str = "213.6px",
    height: str = "128px",
) -> rx.Component:
    """Create a metric card for displaying key metrics."""

    loading_overlay = rx.box(
        rx.center(
            rx.spinner(size="2"),
            width="100%",
            height="100%",
        ),
        style={
            "position": "absolute",
            "inset": 0,
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
            "inset": 0,
            "display": "flex",
            "align_items": "center",
            "justify_content": "center",
            "background_color": "rgba(0,0,0,0.03)",
            "backdrop_filter": T.effects.backdrop_filter_light,
            "z_index": 4,
        },
    )

    overlay = rx.cond(loading, loading_overlay, rx.cond(empty, empty_overlay, None))

    # --- Top (icon + text block) ---
    top_row = rx.hstack(
        # 24x24 icon
        rx.box(
            rx.icon(tag=icon, size=24, color=accent),
            width="24px",
            height="24px",
            flex_shrink="0",
            position="relative",
        ),
        # Text stack (heading + subtitle)
        rx.vstack(
            # Heading: 20/28, medium-ish (510 ≈ 500)
            rx.text(
                value,
                font_family="'SF Pro', ui-sans-serif, system-ui",
                font_size="20px",
                line_height="28px",
                letter_spacing="-0.08px",
                font_weight="500",
                color="#1C2024",
            ),
            rx.cond(
                subtitle,
                rx.text(
                    subtitle,
                    font_family="'SF Pro', ui-sans-serif, system-ui",
                    font_size="14px",
                    line_height="20px",
                    font_weight="400",
                    color="#1C2024",
                ),
                rx.fragment(),
            ),
            align="start",
            spacing="1",
            width="auto",
        ),
        align="center",
        spacing="4",       # 16px gap
        width="100%",
    )

    # --- Metric row (delta + note) ---
    metric_row = rx.cond(
        rx.var(bool(delta) or bool(delta_note)),
        rx.hstack(
            rx.cond(
                delta,
                rx.text(
                    delta,
                    font_family="'SF Pro', ui-sans-serif, system-ui",
                    font_size="14px",
                    line_height="20px",
                    font_weight="400",
                    color="#218358",   # green from spec
                ),
                rx.fragment(),
            ),
            rx.cond(
                delta_note,
                rx.text(
                    delta_note,
                    font_family="'SF Pro', ui-sans-serif, system-ui",
                    font_size="14px",
                    line_height="20px",
                    font_weight="400",
                    color="rgba(0, 7, 20, 0.623529)",
                ),
                rx.fragment(),
            ),
            align="center",
            spacing="1",   # 4px gap
            width="100%",
        ),
        rx.fragment(),
    )

    return rx.card(
        # Content
        rx.vstack(
            top_row,
            metric_row,
            spacing="2",         # 8px gap
            align="start",
            width="100%",
            height="100%",
            justify="center",
        ),
        # Overlays
        overlay,
        # Card chrome copied from CSS
        padding="24px",
        background="#FFFFFF",
        border="1px solid rgba(0, 0, 51, 0.0588235)",
        border_radius="8px",
        width=width,
        height=height,
        style={
            "position": "relative",
            "overflow": "hidden",
            # Multi-shadow stack, verbatim from spec
            "box_shadow": (
                "0px 1px 3px rgba(0,0,0,0.05), "
                "0px 2px 1px -1px rgba(0,0,0,0.05), "
                "0px 1px 4px rgba(0,0,45,0.0901961), "
                "0px 0px 0px 0.5px rgba(0,0,0,0.05)"
            ),
            # Auto-layout bits from spec:
            "box_sizing": "border-box",
            "display": "flex",
            "flex_direction": "column",
            "justify_content": "center",
            "align_items": "flex-start",
            "gap": "8px",
            "align_self": "stretch",
            "flex_grow": 1,
        },
    )
