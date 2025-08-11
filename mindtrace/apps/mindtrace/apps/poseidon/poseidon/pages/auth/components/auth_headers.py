"""Mindtrace Header Components - Animated Page Headers."""

import reflex as rx
from poseidon.styles.variants import COMPONENT_VARIANTS


def auth_headers(title: str, subtitle: str) -> rx.Component:
    """
    Animated page header with staggered animations.
    """
    return rx.vstack(
        rx.text(
            title,
            style={
                **COMPONENT_VARIANTS["header"]["title"],
                "animation": "fadeInUp 0.6s ease-out 0.2s both",
            }
        ),
        rx.text(
            subtitle,
            style={
                **COMPONENT_VARIANTS["header"]["subtitle"],
                "animation": "fadeInUp 0.6s ease-out 0.4s both",
            }
        ),
        spacing="3",
        align="center",
        width="100%",
        margin="0 auto",
    ) 