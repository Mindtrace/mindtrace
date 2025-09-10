"""
Modern registration page component.

Provides user account creation interface with:
- Clean, modern form design using unified Poseidon UI components
- Username, email, and password input fields
- Organization selection (required for multi-tenancy)
- Form validation and error handling
- Responsive design using modern design system
- Consistent with dashboard template styling
"""

import reflex as rx

from poseidon.components.forms import form_input_with_label_and_hint
from poseidon.components_v2.alerts import Alert
from poseidon.components_v2.branding import logo_poseidon
from poseidon.components_v2.containers import card, login_page_container
from poseidon.components_v2.core import link, loader
from poseidon.components_v2.core.button import button
from poseidon.components_v2.layout import main_css_animation
from poseidon.state.auth import AuthState
from poseidon.styles.global_styles import C, Ty
from poseidon.components_v2.forms import registration_form

from .components.auth_headers import auth_headers


def register_content() -> rx.Component:
    """
    Modern registration form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return login_page_container(
        [
            card(
                [
                    rx.box(
                        logo_poseidon(),
                        text_align="center",
                    ),
                    auth_headers("Create your account", "Join the future of intelligent automation"),
                    rx.box(
                        registration_form(
                            title="",
                            subtitle="",
                            submit_label="Create Account",
                            on_submit=AuthState.register,
                        ),
                        style={
                            "width": "100%",
                        },
                    ),
                    rx.box(
                        rx.vstack(
                            link("Already have an account? ", "Sign in", "/"),
                            spacing="2",
                            width="100%",
                        ),
                        border_top=f"1px solid {C.border}",
                        padding_top="1rem",
                        margin_top="1rem",
                    ),
                ]
            ),
        ]
    )


def register_page() -> rx.Component:
    """
    Registration page with dynamic rendering - redirects authenticated users.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            loader(size="large", variant="primary"),
            register_content(),
        ),
        # CSS animations and keyframes
        main_css_animation(),
        on_mount=AuthState.load_available_organizations,
    )
