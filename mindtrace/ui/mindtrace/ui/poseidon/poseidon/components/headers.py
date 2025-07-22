"""
Poseidon Header Components - Unified.

This file contains all header components for Poseidon:
- app_header: The main navigation bar (was header.py)
- page_header, page_header_with_actions, section_header, dashboard_header, breadcrumb_header: Content/section headers
"""

import reflex as rx
from poseidon.state.auth import AuthState
from .mindtrace_headers import header_mindtrace
from .mindtrace_forms import input_mindtrace

# --- App Header (Navigation Bar) ---
def app_header() -> rx.Component:
    """Main app navigation bar with search and user profile."""
    return rx.box(
        rx.hstack(
            # Search section
            rx.box(
                input_mindtrace(
                placeholder="Search datasets, models, devices...",
                    name="search",
                    size="medium",
                ),
                max_width="400px",
                flex="1",
            ),
            # User profile section - simplified
            rx.cond(
                AuthState.is_authenticated,
                rx.hstack(
                    rx.text(
                        f"{AuthState.first_name} {AuthState.last_name}",
                        weight="medium",
                        color=rx.color("slate", 12),
                        size="2",
                    ),
                    rx.button(
                        "Logout",
                        on_click=AuthState.logout,
                        size="2",
                        variant="ghost",
                        color=rx.color("red", 11),
                    ),
                    spacing="3",
                    align="center",
                ),
                # Not authenticated - show login link
                rx.link(
                    "Login",
                    href="/login",
                    color=rx.color("blue", 11),
                    weight="medium",
                ),
            ),
            spacing="4",
            align="center",
            width="100%",
            justify="between",
        ),
        # Header container styling
        padding="1rem 2rem",
        background=rx.color("gray", 1),
        border_bottom=f"1px solid {rx.color('gray', 4)}",
        width="100%",
        height="60px",
        display="flex",
        align_items="center",
        on_mount=AuthState.check_auth,
    )

# --- Page/Section Headers ---

def page_header(
    title: str,
    description: str = "",
    align: str = "center",
    margin_bottom: str = "2rem"
):
    """Standard page header - using mindtrace styling."""
    return rx.box(
        header_mindtrace(title, description),
        text_align=align,
        margin_bottom=margin_bottom,
    )

def page_header_with_actions(
    title: str,
    description: str = "",
    actions: list = None,
    align_content: str = "start"
):
    """Page header with action buttons - keeps Buridan UI styling."""
    if actions is None:
        actions = []
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.heading(
                    title,
                    size="8",
                    weight="bold",
                    color=rx.color("slate", 12),
                    margin_bottom="0.5rem",
                ),
                rx.cond(
                    description,
                    rx.text(
                        description,
                        size="4",
                        color=rx.color("slate", 11),
                    ),
                ),
                spacing="2",
                align="start",
            ),
            rx.spacer(),
            rx.hstack(
                *actions,
                spacing="3",
            ),
            spacing="4",
            align="center",
            width="100%",
        ),
        margin_bottom="2rem",
    )

def section_header(
    title: str,
    subtitle: str = "",
    size: str = "6",
    margin_bottom: str = "1.5rem"
):
    """Section header within pages - using mindtrace styling."""
    return rx.box(
        header_mindtrace(title, subtitle),
        margin_bottom=margin_bottom,
    )

def dashboard_header(
    title: str,
    user_name: str = "",
    stats: list = None
):
    """Dashboard-style header with stats - using mindtrace styling."""
    if stats is None:
        stats = []
    
    subtitle = f"Welcome back, {user_name}!" if user_name else ""
    
    return rx.vstack(
        header_mindtrace(title, subtitle),
        rx.cond(
            stats,
            rx.box(
                rx.hstack(
                    *[
                        rx.vstack(
                            rx.text(
                                stat.get("value", ""),
                                size="6",
                                weight="bold",
                                color=rx.color("slate", 12),
                            ),
                            rx.text(
                                stat.get("label", ""),
                                size="2",
                                color=rx.color("slate", 11),
                            ),
                            spacing="1",
                            align="center",
                        )
                        for stat in stats
                    ],
                    spacing="6",
                    justify="center",
                ),
                padding="1.5rem",
                background=rx.color("gray", 2),
                border_radius="12px",
                border=f"1px solid {rx.color('gray', 6)}",
                margin_bottom="2rem",
            ),
        ),
        spacing="4",
        align="center",
        margin_bottom="3rem",
    )

def breadcrumb_header(
    title: str,
    breadcrumbs: list = None,
    description: str = ""
):
    """Header with breadcrumb navigation - keeps Buridan UI styling."""
    if breadcrumbs is None:
        breadcrumbs = []
    return rx.vstack(
        rx.cond(
            breadcrumbs,
            rx.hstack(
                *[
                    rx.fragment(
                        rx.link(
                            crumb.get("text", ""),
                            href=crumb.get("href", "#"),
                            color=rx.color("blue", 11),
                            size="2",
                        ) if crumb.get("href") else rx.text(
                            crumb.get("text", ""),
                            color=rx.color("slate", 11),
                            size="2",
                        ),
                        rx.cond(
                            i < len(breadcrumbs) - 1,
                            rx.text(" / ", color=rx.color("slate", 9), size="2"),
                        ),
                    )
                    for i, crumb in enumerate(breadcrumbs)
                ],
                spacing="1",
                margin_bottom="1rem",
            ),
        ),
        rx.heading(
            title,
            size="7",
            weight="bold",
            color=rx.color("slate", 12),
        ),
        rx.cond(
            description,
            rx.text(
                description,
                size="3",
                color=rx.color("slate", 11),
                margin_top="0.5rem",
            ),
        ),
        spacing="2",
        align="start",
        margin_bottom="2rem",
    )

 