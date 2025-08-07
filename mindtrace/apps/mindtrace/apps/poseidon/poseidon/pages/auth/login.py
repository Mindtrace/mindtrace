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

from poseidon.styles.global_styles import COLORS

from poseidon.state.auth import AuthState

from poseidon.components_v2.core import loader, link
from poseidon.components_v2.branding import logo_poseidon
from poseidon.components_v2.layout import main_css_animation
from poseidon.components_v2.containers import card, full_page_container

from .components.login_form import login_form
from .components.auth_headers import auth_headers

def login_content() -> rx.Component:
    """
    Modern login form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return full_page_container([
        card([
            rx.box(
                logo_poseidon(),
                text_align="center",
            ),
            auth_headers(
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
                    link(
                        "Don't have an account? ",
                        "Sign up",
                        "/register"
                    ),
                    link(
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
            loader(size="large", variant="primary"),
            login_content(),
        ),
        # CSS animations and keyframes
        main_css_animation(),
    ) 