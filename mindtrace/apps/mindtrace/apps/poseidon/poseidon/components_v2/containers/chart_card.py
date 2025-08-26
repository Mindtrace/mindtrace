"""Chart Card Component for Poseidon - Reusable card container for charts."""

import reflex as rx
from typing import Optional

from poseidon.styles.global_styles import THEME as T


def chart_card(
    title: str,
    subtitle: Optional[str] = None,
    children: Optional[rx.Component] = None,
    card_variant: str = "default",
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
        style=card_styles,
        width="100%",
    ) 