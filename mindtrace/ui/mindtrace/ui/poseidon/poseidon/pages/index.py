"""
Simple home page component.

Provides a clean welcome page with:
- Welcome header using unified Poseidon UI components
- Navigation options using unified navigation cards
- Clean modern styling
"""

import reflex as rx
from poseidon.components import sidebar, app_header, navigation_action_card, page_header, page_container, card_grid
from poseidon.state.auth import AuthState


def index() -> rx.Component:
    """
    Simple home page with clean layout using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return rx.box(
        # Conditional sidebar - only show for authenticated users
        rx.cond(
            AuthState.is_authenticated,
            rx.box(
                sidebar(),
                position="fixed",
                left="0",
                top="0",
                width="240px",
                height="100vh",
                z_index="1000",
            ),
        ),
        # Conditional header - only show for authenticated users
        rx.cond(
            AuthState.is_authenticated,
            rx.box(
                app_header(),
                position="fixed",
                top="0",
                left="240px",
                right="0",
                height="60px",
                z_index="999",
            ),
        ),
        # Main content area with conditional margin and unified layout
        rx.box(
            # Welcome section using unified page_header
            page_header(
                title="Welcome to Poseidon Toolkit",
                description="Your industrial AI platform for intelligent automation",
                margin_bottom="3rem",
            ),
            # Navigation cards for authenticated users
            rx.cond(
                AuthState.is_authenticated,
                rx.vstack(
                    rx.text(
                        f"Hello, {AuthState.current_username}!",
                        size="5",
                        color=rx.color("slate", 12),
                        weight="medium",
                        margin_bottom="2rem",
                    ),
                    card_grid(
                        rx.link(
                            navigation_action_card(
                                title="Profile",
                                description="View and manage your account settings",
                                icon="👤",
                            ),
                            href="/profile",
                            text_decoration="none",
                        ),
                        rx.cond(
                            AuthState.is_super_admin,
                            rx.link(
                                navigation_action_card(
                                    title="Super Admin",
                                    description="System-wide management and configuration",
                                    icon="🔧",
                                ),
                                href="/super-admin-dashboard",
                                text_decoration="none",
                            ),
                            rx.cond(
                                AuthState.is_admin,
                                rx.link(
                                    navigation_action_card(
                                        title="Admin Panel",
                                        description="Organization administration and user management",
                                        icon="⚙️",
                                    ),
                                    href="/admin",
                                    text_decoration="none",
                                ),
                            ),
                        ),
                        min_card_width="280px",
                        max_width="700px",
                        justify_content="center",
                    ),
                    spacing="6",
                    align="center",
                ),
                # For non-authenticated users
                rx.vstack(
                    rx.text(
                        "Please sign in to access your workspace",
                        color=rx.color("slate", 11),
                        size="4",
                        margin_bottom="2rem",
                    ),
                    card_grid(
                        rx.link(
                            navigation_action_card(
                                title="Sign In",
                                description="Access your account and workspace",
                                icon="🔑",
                            ),
                            href="/login",
                            text_decoration="none",
                        ),
                        rx.link(
                            navigation_action_card(
                                title="Register",
                                description="Create a new account to get started",
                                icon="📝",
                            ),
                            href="/register",
                            text_decoration="none",
                        ),
                        min_card_width="280px",
                        max_width="700px",
                        justify_content="center",
                    ),
                    spacing="6",
                    align="center",
                ),
            ),
            # Conditional styling - adjust margin based on auth status
            margin_left=rx.cond(AuthState.is_authenticated, "16rem", "0"),
            margin_top=rx.cond(AuthState.is_authenticated, "60px", "0"),
            padding="2rem",
            min_height="100vh",
            background=rx.color("gray", 1),
            display="flex",
            flex_direction="column",
            align_items="center",
            justify_content="center",
        ),
        # Overall container
        width="100%",
        height="100vh",
        position="relative",
        # Initialize auth check
        on_mount=AuthState.check_auth,
    ) 