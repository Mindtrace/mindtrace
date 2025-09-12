"""Chart Card Component for Poseidon - Reusable card container for charts."""

import reflex as rx
from typing import Optional

from poseidon.styles.global_styles import THEME as T


def chart_card(
    title: str,
    subtitle: Optional[str] = None,
    children: Optional[rx.Component] = None,
    card_variant: str = "default",
    loading: bool = False,
    empty: bool = False,
    empty_message: str = "No data",
) -> rx.Component:
    """
    Create a card container for charts or other components.
    
    This is a generic card component that can wrap any content with consistent
    styling that matches the Poseidon design system.

    Args:
        title: Card title
        subtitle: Card subtitle
        children: The component to be wrapped in the card (e.g., a chart)
        card_variant: Card styling variant ("default" or "interactive")
        loading: Show a full-card overlay with a spinner
        empty: Show a full-card overlay with an empty state
        empty_message: Message to show in the empty overlay

    Returns:
        A Reflex component containing the children in a card
    """

    # Card styles based on variant
    card_styles = {
        "background": T.colors.surface,
        "backdrop_filter": T.effects.backdrop_filter,
        "border_radius": T.radius.r_xl,
        "border": f"1px solid {T.colors.border}",
        "box_shadow": T.shadows.shadow_2,
        "padding": T.spacing.space_4,
        "padding_bottom": 0,
        "position": "relative",
        "overflow": "hidden",
        "transition": T.motion.dur,
    }

    # Add hover effects for interactive cards
    if card_variant == "interactive":
        card_styles.update(
            {
                "_hover": {
                    # "transform": "translateY(-4px)",
                    "box_shadow": T.shadows.shadow_2,
                    "border_color": T.colors.accent,
                }
            }
        )

    # Full-card overlays
    loading_overlay = rx.box(
        rx.center(
            rx.spinner(size="3"),
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
            rx.vstack(
                rx.icon("circle-off"),
                rx.text(empty_message, color=T.colors.fg_muted),
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

    # Create the card container
    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.text(
                    title,
                    font_size=T.typography.fs_lg,
                    font_weight=T.typography.fw_600,
                    color=T.colors.fg,
                    text_align="center",
                ),
                rx.text(
                    subtitle,
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_muted,
                    text_align="center",
                )
                if subtitle
                else None,
                spacing="1",
            ),
            children,
            spacing="1",
            width="100%",
        ),
        overlay,
        style=card_styles,
        width="100%",
    ) 