"""Poseidon Button Components - Buridan UI Styling.

Action buttons for Poseidon use cases while keeping
the exact Buridan UI styling patterns.
"""

import reflex as rx


def primary_action_button(
    text: str,
    on_click=None,
    loading: bool = False,
    disabled: bool = False,
    icon: str = "",
    size: str = "3",
    width: str = "auto"
):
    """Primary action button - keeps Buridan UI styling."""
    return rx.button(
        rx.cond(
            icon,
            rx.hstack(
                rx.text(icon, margin_right="8px"),
                rx.text(text),
                spacing="1",
                align="center",
            ),
            rx.text(text),
        ),
        on_click=on_click,
        loading=loading,
        disabled=disabled,
        variant="solid",
        color_scheme="blue",
        size=size,
        width=width,
        cursor="pointer",
    )


def secondary_action_button(
    text: str,
    on_click=None,
    loading: bool = False,
    disabled: bool = False,
    icon: str = "",
    size: str = "3",
    width: str = "auto"
):
    """Secondary action button - keeps Buridan UI styling."""
    return rx.button(
        rx.cond(
            icon,
            rx.hstack(
                rx.text(icon, margin_right="8px"),
                rx.text(text),
                spacing="1",
                align="center",
            ),
            rx.text(text),
        ),
        on_click=on_click,
        loading=loading,
        disabled=disabled,
        variant="surface",
        color_scheme="gray",
        size=size,
        width=width,
        cursor="pointer",
    )


def refresh_button(
    on_click=None,
    loading: bool = False,
    text: str = "Refresh",
    icon: str = "🔄"
):
    """Refresh/reload data button - keeps Buridan UI styling."""
    return rx.button(
        rx.hstack(
            rx.text(icon, margin_right="8px"),
            rx.text(text),
            spacing="1",
            align="center",
        ),
        on_click=on_click,
        loading=loading,
        variant="surface",
        color_scheme="gray",
        size="2",
        cursor="pointer",
    )


def danger_action_button(
    text: str,
    on_click=None,
    loading: bool = False,
    disabled: bool = False,
    icon: str = "",
    size: str = "3",
    width: str = "auto"
):
    """Danger action button - keeps Buridan UI styling."""
    return rx.button(
        rx.cond(
            icon,
            rx.hstack(
                rx.text(icon, margin_right="8px"),
                rx.text(text),
                spacing="1",
                align="center",
            ),
            rx.text(text),
        ),
        on_click=on_click,
        loading=loading,
        disabled=disabled,
        variant="solid",
        color_scheme="red",
        size=size,
        width=width,
        cursor="pointer",
    )


def success_action_button(
    text: str,
    on_click=None,
    loading: bool = False,
    disabled: bool = False,
    icon: str = "",
    size: str = "3",
    width: str = "auto"
):
    """Success action button - keeps Buridan UI styling."""
    return rx.button(
        rx.cond(
            icon,
            rx.hstack(
                rx.text(icon, margin_right="8px"),
                rx.text(text),
                spacing="1",
                align="center",
            ),
            rx.text(text),
        ),
        on_click=on_click,
        loading=loading,
        disabled=disabled,
        variant="solid",
        color_scheme="green",
        size=size,
        width=width,
        cursor="pointer",
    )


def icon_button(
    icon: str,
    on_click=None,
    loading: bool = False,
    disabled: bool = False,
    variant: str = "ghost",
    color_scheme: str = "gray",
    size: str = "2"
):
    """Icon-only button - keeps Buridan UI styling."""
    return rx.button(
        rx.text(icon),
        on_click=on_click,
        loading=loading,
        disabled=disabled,
        variant=variant,
        color_scheme=color_scheme,
        size=size,
        cursor="pointer",
    )


def link_button(
    text: str,
    href: str,
    icon: str = "",
    size: str = "2",
    color: str = "blue"
):
    """Link-style button - keeps Buridan UI styling."""
    return rx.link(
        rx.cond(
            icon,
            rx.hstack(
                rx.text(icon, margin_right="8px"),
                rx.text(text),
                spacing="1",
                align="center",
            ),
            rx.text(text),
        ),
        href=href,
        color=rx.color(color, 11),
        weight="medium",
        size=size,
        text_decoration="none",
        _hover={"text_decoration": "underline"},
    )


def action_button_group(*buttons, spacing: str = "3", justify: str = "start"):
    """Group of action buttons - keeps Buridan UI styling."""
    return rx.hstack(
        *buttons,
        spacing=spacing,
        justify=justify,
        align="center",
    )


# Keep original demo button for reference
def button_v1():
    """Original Buridan UI demo button - for reference."""
    return rx.button(
        "Buridan UI Button",
        variant="solid",
        color_scheme="blue",
        size="3",
        cursor="pointer",
    ) 