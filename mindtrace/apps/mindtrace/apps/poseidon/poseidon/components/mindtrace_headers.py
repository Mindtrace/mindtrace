"""Mindtrace Header Components - Animated Page Headers."""

import reflex as rx


def header_mindtrace(title: str, subtitle: str) -> rx.Component:
    """
    Animated page header with staggered animations.
    """
    return rx.vstack(
        rx.text(
            title,
            style={
                "font_size": "2.25rem",
                "font_weight": "700",
                "color": "rgb(15, 23, 42)",
                "line_height": "1.1",
                "font_family": '"Inter", system-ui, sans-serif',
                "letter_spacing": "-0.025em",
                "text_align": "center",
                "animation": "fadeInUp 0.6s ease-out 0.2s both",
            }
        ),
        rx.text(
            subtitle,
            style={
                "font_size": "1rem",
                "font_weight": "400",
                "color": "rgb(100, 116, 139)",
                "line_height": "1.5",
                "font_family": '"Inter", system-ui, sans-serif',
                "text_align": "center",
                "animation": "fadeInUp 0.6s ease-out 0.4s both",
            }
        ),
        spacing="3",
        align="center",
        width="100%",
        margin="0 auto",
    ) 