"""
User profile page component.

Displays user profile information with:
- Profile information cards using unified Poseidon UI components
- User statistics display
- Clean layout with sidebar and header
"""

import reflex as rx
from poseidon.components import (
    sidebar, app_header, profile_info_card, user_profile_stats, 
    page_header, page_container, authenticated_page_wrapper
)
from poseidon.state.auth import AuthState


def profile_content() -> rx.Component:
    """
    Profile page content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return rx.box(
        page_container(
            rx.center(
                rx.vstack(
                    # Page header with better spacing
                    rx.vstack(
                        page_header(
                            title="Profile",
                            description="Manage your account information and settings",
                        ),
                        spacing="0",
                        margin_bottom="3rem",
                        align="center",
                    ),
                    # Stats section at the top
                    rx.vstack(
                        rx.heading("Account Overview", size="3", margin_bottom="1rem", text_align="center"),
                        user_profile_stats(),
                        spacing="2",
                        margin_bottom="3rem",
                        align="center",
                    ),
                    # Account information card with improved content
                    profile_info_card(
                        title="Account Information",
                        content_items=[
                            {"label": "Username", "value": AuthState.current_username},
                            {"label": "User ID", "value": AuthState.user_id},
                            {"label": "Organization ID", "value": AuthState.user_organization_id},
                            {"label": "Organization Role", "value": rx.cond(
                                AuthState.user_org_role != "",
                                AuthState.role_display,
                                "No role assigned"
                            )},
                            {"label": "Admin Status", "value": rx.cond(
                                AuthState.is_super_admin,
                                "Super Admin",
                                rx.cond(
                                    AuthState.is_admin,
                                    "Organization Admin",
                                    "Regular User"
                                )
                            )},
                            {"label": "Authentication Status", "value": "Active"},
                        ]
                    ),
                    spacing="0",
                    width="100%",
                    max_width="900px",
                    align="center",
                ),
                width="100%",
            ),
            margin_top="60px",  # Account for header
        ),
        width="100%",
        min_height="100vh",
        position="relative",
        # Initialize auth check
        on_mount=AuthState.check_auth,
    )


def profile_page() -> rx.Component:
    """
    Profile page with authentication check.
    Uses unified authentication wrapper for consistency.
    """
    return authenticated_page_wrapper(profile_content) 