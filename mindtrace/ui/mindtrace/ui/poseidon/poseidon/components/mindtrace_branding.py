"""Mindtrace Branding Components - Logo and Brand Elements."""

import reflex as rx


def logo_mindtrace() -> rx.Component:
    """
    Professional logo design with mindtrace styling.
    """
    return rx.box(
        rx.hstack(
            # Brand text section
            rx.vstack(
                rx.text(
                    "Poseidon",
                    style={
                        "font_size": "2.5rem",
                        "font_weight": "700",
                        "line_height": "1.0",
                        "font_family": '"Inter", system-ui, sans-serif',
                        "letter_spacing": "-0.02em",
                        "color": "#0057FF",
                        "margin": "0",
                    }
                ),
                rx.text(
                    "AI PLATFORM",
                    style={
                        "font_size": "0.75rem",
                        "font_weight": "500",
                        "letter_spacing": "0.15em",
                        "color": "rgba(100, 116, 139, 0.7)",
                        "text_transform": "uppercase",
                        "margin": "0",
                        "font_family": '"Inter", system-ui, sans-serif',
                    }
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