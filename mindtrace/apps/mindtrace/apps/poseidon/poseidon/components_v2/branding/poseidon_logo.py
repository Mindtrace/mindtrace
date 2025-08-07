"""Poseidon Branding Components - Logo and Brand Elements."""

import reflex as rx
from poseidon.styles.variants import COMPONENT_VARIANTS


def logo_poseidon() -> rx.Component:
    """
    Professional logo design with Poseidon styling.
    """
    return rx.box(
        rx.hstack(
            # Brand text section
            rx.vstack(
                rx.text(
                    "Poseidon",
                    style=COMPONENT_VARIANTS["logo"]["title"]
                ),
                rx.text(
                    "AI PLATFORM",
                    style=COMPONENT_VARIANTS["logo"]["subtitle"]
                ),
                spacing="1",
                align="start",
                margin_left="1rem",
            ),
            align="center",
            spacing="0",
        ),
        margin_bottom="2rem",
        width="100%",
    ) 