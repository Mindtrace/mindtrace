"""Poseidon Branding Components - Logo and Brand Elements."""

import reflex as rx
from poseidon.styles.variants import COMPONENT_VARIANTS


def logo_inspectra() -> rx.Component:
    """
    Professional logo design with Inspectra styling.
    """
    return rx.box(
        rx.hstack(
            # Brand text section
            rx.text(
                "Inspectra",
                style=COMPONENT_VARIANTS["logo"]["title"],
                color="#60CCA5",
            ),
            spacing="1",
            align="center",
            margin_left="1rem",
            justify="center",
        ),
        margin_bottom="2rem",
        width="100%",
    ) 