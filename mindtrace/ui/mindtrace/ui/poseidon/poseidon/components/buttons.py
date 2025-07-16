"""Poseidon Button Components - Buridan UI Styling.

Action buttons for Poseidon use cases while keeping
the exact Buridan UI styling patterns.
"""

import reflex as rx
from .mindtrace_forms import button_mindtrace


# Removed: primary_action_button - use mindtrace_forms.button_mindtrace instead


# Removed: secondary_action_button - use mindtrace_forms.button_mindtrace instead


def refresh_button(
    on_click=None,
    loading: bool = False,
    text: str = "Refresh",
    icon: str = "🔄"
):
    """Refresh/reload data button - using mindtrace styling."""
    return button_mindtrace(
        text=f"{icon} {text}",
        on_click=on_click,
        loading=loading,
        variant="secondary",
        size="medium",
    )


# Removed: danger_action_button - use mindtrace_forms.button_mindtrace with variant="danger"


# Removed: success_action_button - use mindtrace_forms.button_mindtrace instead


def icon_button(
    icon: str,
    on_click=None,
    loading: bool = False,
    disabled: bool = False,
    variant: str = "ghost",
    color_scheme: str = "gray",
    size: str = "2"
):
    """Icon-only button - using mindtrace styling."""
    # Map legacy variant to mindtrace variant
    mindtrace_variant = "secondary" if variant == "ghost" else "primary"
    mindtrace_size = "small" if size == "1" else "medium" if size == "2" else "large"
    
    return button_mindtrace(
        text=icon,
        on_click=on_click,
        loading=loading,
        disabled=disabled,
        variant=mindtrace_variant,
        size=mindtrace_size,
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


 