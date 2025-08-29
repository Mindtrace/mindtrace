"""Test file for the tabs container component."""

import reflex as rx
from poseidon.components_v2.containers.tabs_container import (
    tabs_container,
    horizontal_tabs,
    vertical_tabs,
    pill_tabs,
    underline_tabs,
    card_tabs,
)
from poseidon.styles.global_styles import THEME as T


def test_tabs_container():
    """Test the tabs container with various configurations."""
    
    # Sample tabs data
    sample_tabs = [
        {
            "label": "Overview",
            "value": "overview",
            "icon": "📊",
            "content": rx.text("Overview content", color=T.colors.fg),
        },
        {
            "label": "Settings",
            "value": "settings",
            "icon": "⚙️",
            "content": rx.text("Settings content", color=T.colors.fg),
        },
        {
            "label": "Profile",
            "value": "profile",
            "icon": "👤",
            "content": rx.text("Profile content", color=T.colors.fg),
        },
    ]
    
    # Test different variants
    return rx.vstack(
        rx.heading("Tabs Container Test", size="4", color=T.colors.fg),
        
        # Default horizontal tabs
        rx.vstack(
            rx.heading("Default Horizontal", size="3", color=T.colors.fg),
            horizontal_tabs(sample_tabs),
            spacing="4",
            align_items="start",
            width="100%",
        ),
        
        # Pill tabs
        rx.vstack(
            rx.heading("Pill Tabs", size="3", color=T.colors.fg),
            pill_tabs(sample_tabs),
            spacing="4",
            align_items="start",
            width="100%",
        ),
        
        # Underline tabs
        rx.vstack(
            rx.heading("Underline Tabs", size="3", color=T.colors.fg),
            underline_tabs(sample_tabs),
            spacing="4",
            align_items="start",
            width="100%",
        ),
        
        # Card tabs
        rx.vstack(
            rx.heading("Card Tabs", size="3", color=T.colors.fg),
            card_tabs(sample_tabs),
            spacing="4",
            align_items="start",
            width="100%",
        ),
        
        # Vertical tabs
        rx.vstack(
            rx.heading("Vertical Tabs", size="3", color=T.colors.fg),
            rx.hstack(
                vertical_tabs(sample_tabs),
                spacing="6",
                align_items="start",
                width="100%",
            ),
            spacing="4",
            align_items="start",
            width="100%",
        ),
        
        spacing="6",
        align_items="start",
        width="100%",
        padding="2rem",
    )


if __name__ == "__main__":
    # This would be used if running the test directly
    print("Tabs container test created successfully!") 