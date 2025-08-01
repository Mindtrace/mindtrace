"""
Modern registration page component.

Provides user account creation interface with:
- Clean, modern form design using unified Poseidon UI components
- First name, last name, email, and password input fields
- Organization selection (required for multi-tenancy)
- Form validation and error handling
- Responsive design using modern design system
- Consistent with dashboard template styling
"""

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.components import (
    registration_form, 
    error_message, redirect_component,
    logo_mindtrace, card_mindtrace, header_mindtrace,
    button_mindtrace, link_mindtrace, page_layout_mindtrace, css_animations_mindtrace,
)
from poseidon.components.forms import form_input_with_label_and_hint


def register_content() -> rx.Component:
    """
    Modern registration form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return page_layout_mindtrace([
        card_mindtrace([
            rx.box(
                logo_mindtrace(),
                text_align="center",
            ),
            header_mindtrace(
                "Create your account",
                "Join the future of intelligent automation"
            ),
            rx.box(
                registration_form(
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
                    link_mindtrace(
                        "Are you an organization admin? ",
                        "Register as Admin",
                        "/register-admin"
                    ),
                    link_mindtrace(
                        "Already have an account? ",
                        "Sign in",
                        "/login"
                    ),
                    spacing="2",
                    width="100%",
                ),
                border_top="1px solid rgba(226, 232, 240, 0.5)",
                padding_top="1rem",
                margin_top="1rem",
            ),
        ]),
    ])


def register_admin_content() -> rx.Component:
    """
    """
    return page_layout_mindtrace([
        card_mindtrace([
            rx.box(
                logo_mindtrace(),
                text_align="center",
            ),
            header_mindtrace(
                "Admin Registration",
                "Create your organization admin account"
            ),
            rx.box(
                registration_form(
                    title="",
                    subtitle="",
                    extra_fields=[
                        form_input_with_label_and_hint(
                        "Admin Registration Key", 
                        "Admin Registration Key", 
                        "💡 Get your admin key from your super admin",
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
                link_mindtrace(
                    "Need a regular user account? ",
                    "User Registration",
                    "/register"
                ),
                border_top="1px solid rgba(226, 232, 240, 0.5)",
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
    return page_layout_mindtrace([
        card_mindtrace([
            rx.box(
                logo_mindtrace(),
                text_align="center",
            ),
            rx.box(
                rx.text(
                    "🔐 Super Admin Registration",
                    style={
                        "font_size": "1.875rem",
                        "font_weight": "700",
                        "color": "#DC2626",
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
                        "color": "#B91C1C",
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
                    form_input_with_label_and_hint("First Name", "First Name", "", "text", "first_name", True, "medium"),
                    form_input_with_label_and_hint("Last Name", "Last Name", "", "text", "last_name", True, "medium"),
                    form_input_with_label_and_hint("Email", "Email address", "", "email", "email", True, "medium"),
                    form_input_with_label_and_hint("Password", "Password", "", "password", "password", True, "medium"),
                    form_input_with_label_and_hint("Super Admin Master Key", "Super Admin Master Key", "", "password", "super_admin_key", True, "medium"),
                    button_mindtrace(
                        "🔐 Create Super Admin Account",
                        button_type="submit",
                        variant="danger",
                        size="medium"
                    ),
                    rx.cond(
                        AuthState.error,
                        rx.box(
                            error_message(AuthState.error),
                            style={"animation": "shake 0.5s ease-in-out"}
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
                    link_mindtrace(
                        "Need regular account? ",
                        "User Registration",
                        "/register"
                    ),
                    link_mindtrace(
                        "Already have an account? ",
                        "Sign in",
                        "/login"
                    ),
                    spacing="2",
                    width="100%",
                ),
                border_top="1px solid rgba(226, 232, 240, 0.5)",
                # padding_top="1rem",
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
            redirect_component("Redirecting to dashboard..."),
            register_content(),
        ),
        # CSS animations and keyframes
        css_animations_mindtrace(),
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
            redirect_component("Redirecting to dashboard..."),
            register_admin_content(),
        ),
        # CSS animations and keyframes
        css_animations_mindtrace(),
    )


def register_super_admin_page() -> rx.Component:
    """
    Super admin registration page with dynamic rendering.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            redirect_component("Redirecting to dashboard..."),
            register_super_admin_content(),
        ),
        # CSS animations and keyframes
        css_animations_mindtrace(),
    ) 