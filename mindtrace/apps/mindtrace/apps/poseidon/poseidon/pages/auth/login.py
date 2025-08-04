"""
Modern login page component.

Provides user authentication interface with:
- Clean, modern form design using unified Poseidon UI components
- Email and password input fields
- Form validation and error handling
- Responsive design using modern design system
- Consistent with dashboard template styling
"""

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.components import (
    login_form, redirect_component,
    logo_mindtrace, card_mindtrace, header_mindtrace,
    link_mindtrace, page_layout_mindtrace, css_animations_mindtrace,
)
from poseidon.styles.global_styles import COLORS


def login_content() -> rx.Component:
    """
    Modern login form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return page_layout_mindtrace([
        card_mindtrace([
            rx.box(
                logo_mindtrace(),
                text_align="center",
            ),
            header_mindtrace(
                "Sign in to your account",
                "Welcome back! Enter your credentials to access your workspace"
            ),
            rx.box(
                login_form(
                    title="",
                    subtitle=""
                ),
                style={
                    "width": "100%",
                }
            ),
            rx.box(
                rx.vstack(
                    link_mindtrace(
                        "Don't have an account? ",
                        "Sign up",
                        "/register"
                    ),
                    link_mindtrace(
                        "Need admin access? ",
                        "Admin Registration",
                        "/register-admin"
                    ),
                    spacing="2",
                    width="100%",
                ),
                border_top=f"1px solid {COLORS['border_divider']}",
                padding_top="1rem",
                margin_top="1rem",
            ),
        ]),
    ])


def login_page() -> rx.Component:
    """
    Login page with dynamic rendering - redirects authenticated users.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            redirect_component("Redirecting to dashboard..."),
            login_content(),
        ),
        # CSS animations and keyframes
        css_animations_mindtrace(),
    ) 