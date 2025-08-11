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
from poseidon.state.auth import AuthState

from poseidon.components_v2.core import loader, link
from poseidon.components_v2.branding import logo_poseidon
from poseidon.components_v2.layout import main_css_animation
from poseidon.components_v2.containers import card, full_page_container

from .components.register_form import register_form
from .components.auth_headers import auth_headers


from poseidon.components_v2.alerts import Alert
from poseidon.components_v2.core.button import button
from poseidon.components.forms import form_input_with_label_and_hint
from poseidon.styles.global_styles import COLORS


def register_content() -> rx.Component:
    """
    Modern registration form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return full_page_container([
        card([
            rx.box(
                logo_poseidon(),
                text_align="center",
            ),
            auth_headers(
                "Create your account",
                "Join the future of intelligent automation"
            ),
            rx.box(
                register_form(
                    title="",
                    subtitle="",
                    submit_label="Create Account",
                    on_submit=AuthState.register,
                ),
                style={
                    "width": "100%",
                }
            ),
            rx.box(
                rx.vstack(
                    link(
                        "Are you an organization admin? ",
                        "Register as Admin",
                        "/register-admin"
                    ),
                    link(
                        "Already have an account? ",
                        "Sign in",
                        "/login"
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


def register_admin_content() -> rx.Component:
    """
    """
    return full_page_container([
        card([
            rx.box(
                logo_poseidon(),
                text_align="center",
            ),
            auth_headers(
                "Admin Registration",
                "Create your organization admin account"
            ),
            rx.box(
                register_form(
                    title="",
                    subtitle="",
                    extra_fields=[
                        form_input_with_label_and_hint(
                        "Admin Registration Key", 
                        "Admin Registration Key", 
                        "Get your admin key from your super admin",
                        "password", 
                        "admin_key", 
                        True,
                        "medium"
                    ),
                    ],
                    submit_label="Create Admin Account",
                    on_submit=AuthState.register_admin,
                ),
                style={
                    "width": "100%",
                }
            ),
            rx.box(
                link(
                    "Need a regular user account? ",
                    "User Registration",
                    "/register"
                ),
                border_top=f"1px solid {COLORS['border_divider']}",
                padding_top="1rem",
                margin_top="1rem",
            ),
        ]),
    ])


def register_super_admin_content() -> rx.Component:
    """
    Super admin registration form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return full_page_container([
        card([
            rx.box(
                logo_poseidon(),
                text_align="center",
            ),
            rx.box(
                rx.text(
                    "Super Admin Registration",
                    style={
                        "font_size": "1.875rem",
                        "font_weight": "700",
                        "color": COLORS["secondary"],
                        "line_height": "1.1",
                        "font_family": '"Inter", system-ui, sans-serif',
                        "letter_spacing": "-0.025em",
                        "text_align": "center",
                        "margin_bottom": "0.5rem",
                    }
                ),
                rx.text(
                    "Master key required for super admin access",
                    style={
                        "font_size": "1rem",
                        "font_weight": "500",
                        "color": COLORS["secondary_dark"],
                        "line_height": "1.4",
                        "font_family": '"Inter", system-ui, sans-serif',
                        "text_align": "center",
                        "font_style": "italic",
                        "margin_bottom": "1.5rem",
                    }
                ),
            ),
            rx.form(
                rx.vstack(
                    form_input_with_label_and_hint("Username", "Username", "", "text", "username", True, "medium"),
                    form_input_with_label_and_hint("Email", "Email address", "", "email", "email", True, "medium"),
                    form_input_with_label_and_hint("Password", "Password", "", "password", "password", True, "medium"),
                    form_input_with_label_and_hint("Super Admin Master Key", "Super Admin Master Key", "", "password", "super_admin_key", True, "medium"),
                    button(
                        "Create Super Admin Account",
                        button_type="submit",
                        variant="danger",
                        size="medium"
                    ),
                    rx.cond(
                        AuthState.error,
                        rx.box(
                            Alert.create(
                                severity="error",
                                title="Error",
                                message=AuthState.error,
                            ),
                            style={"animation": "shake 0.5s ease-in-out", "width": "100%"}
                        ),
                    ),
                    width="100%",
                    spacing="1",
                ),
                on_submit=AuthState.register_super_admin,
                width="100%",
            ),
            # Links section
            rx.box(
                rx.vstack(
                    link(
                        "Need regular account? ",
                        "User Registration",
                        "/register"
                    ),
                    link(
                        "Already have an account? ",
                        "Sign in",
                        "/login"
                    ),
                    spacing="2",
                    width="100%",
                ),
                border_top=f"1px solid {COLORS['border_divider']}",
                margin_top="1rem",
            ),
        ]),
    ])


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


def register_admin_page() -> rx.Component:
    """
    Admin registration page with dynamic rendering.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            loader(size="large", variant="primary"),
            register_admin_content(),
        ),
        # CSS animations and keyframes
        main_css_animation(),
    )


def register_super_admin_page() -> rx.Component:
    """
    Super admin registration page with dynamic rendering.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            loader(size="large", variant="primary"),
            register_super_admin_content(),
        ),
        # CSS animations and keyframes
        main_css_animation(),
    ) 