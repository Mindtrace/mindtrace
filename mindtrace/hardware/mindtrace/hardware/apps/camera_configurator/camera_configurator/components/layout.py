"""Layout components for the camera configurator following Reflex best practices."""

import reflex as rx

from ..styles.theme import colors, css_spacing, layout, radius, shadows


def main_layout(content: rx.Component) -> rx.Component:
    """Main application layout following Poseidon patterns with proper viewport handling."""
    return rx.box(
        content,
        background="linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)",
        min_height="100vh",
        width="100%",
    )


def page_container(content: rx.Component, title: str = "") -> rx.Component:
    """Proper page container using Reflex container with consistent max-width and centering."""
    return rx.container(
        rx.cond(
            title != "",
            rx.box(
                rx.heading(
                    title,
                    size="8",
                    color=colors["gray_900"],
                    margin_bottom=layout["content_gap"],
                ),
                content,
                display="flex",
                flex_direction="column",
                gap=layout["section_gap"],
                width="100%",
            ),
            content,
        ),
        size="4",  # 1136px max-width from Reflex docs
        padding=layout["content_padding"],
        width="100%",
    )


def header_card(content: rx.Component) -> rx.Component:
    """Header card with enhanced styling and proper spacing."""
    return rx.box(
        content,
        background="linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)",
        border=f"1px solid {colors['border']}",
        border_radius=radius["xl"],
        box_shadow=shadows["lg"],
        padding=css_spacing["xl"],
        margin_bottom=layout["section_gap"],
        width="100%",
    )


def control_panel(content: rx.Component) -> rx.Component:
    """Control panel with modern card styling and proper spacing."""
    return rx.box(
        content,
        background=colors["white"],
        border=f"1px solid {colors['border']}",
        border_radius=radius["lg"],
        box_shadow=shadows["md"],
        padding=css_spacing["lg"],
        margin_bottom=layout["section_gap"],
        width="100%",
    )
