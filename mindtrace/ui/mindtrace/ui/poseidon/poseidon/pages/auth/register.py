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
from poseidon.components import (
    registration_form, primary_action_button, danger_action_button, 
    error_message, link_button, centered_form_layout, redirect_component
)


def register_content() -> rx.Component:
    """
    Modern registration form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return centered_form_layout(
        rx.vstack(
            registration_form(
                title="Create your Poseidon account",
                subtitle="Join the industrial AI platform for intelligent automation"
            ),
            rx.box(
                rx.text(
                    "Are you an organization admin? ",
                    color=rx.color("slate", 11),
                    display="inline",
                ),
                rx.link(
                    "Register as Admin",
                    href="/register-admin",
                    color=rx.color("blue", 11),
                    weight="medium",
                ),
                text_align="center",
                margin_top="1rem",
            ),
            rx.box(
                rx.text(
                    "Already have an account? ",
                    color=rx.color("slate", 11),
                    display="inline",
                ),
                rx.link(
                    "Sign in",
                    href="/login",
                    color=rx.color("blue", 11),
                    weight="medium",
                ),
                text_align="center",
                margin_top="0.5rem",
            ),
            spacing="4",
        ),
        max_width="450px"
    )


def register_admin_content() -> rx.Component:
    """
    Admin registration form content using unified Poseidon UI components and styling.
    All state and event logic is handled in the page/state, not in the components.
    """
    return centered_form_layout(
        rx.vstack(
            registration_form(
                title="Create Organization Admin Account",
                subtitle="Register as an organization admin. You will need an admin registration key from your super admin.",
                extra_fields=[
                    # Admin key input and helper text
                    rx.vstack(
                        rx.input(
                            placeholder="Admin Registration Key (ask your super admin)",
                            name="admin_key",
                            type="password",
                            required=False,
                            class_name="w-full p-2 text-sm rounded-md bg-transparent border border-gray-500/40 focus:outline-none focus:border-blue-500 shadow-sm",
                        ),
                        rx.text(
                            "This key is required to register as an organization admin. Get it from your super admin.",
                            size="2",
                            color=rx.color("orange", 10),
                            margin_bottom="0.5rem",
                            font_style="italic",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ],
                submit_label="Create Admin Account",
                on_submit=AuthState.register_admin,
            ),
            rx.box(
                rx.text(
                    "Need a regular user account? ",
                    color=rx.color("slate", 11),
                    display="inline",
                ),
                rx.link(
                    "User Registration",
                    href="/register",
                    color=rx.color("blue", 11),
                    weight="medium",
                ),
                text_align="center",
                margin_top="1rem",
            ),
            spacing="4",
        ),
        max_width="450px"
    )


def register_super_admin_content() -> rx.Component:
    """
    Super admin registration form content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return centered_form_layout(
        rx.box(
            rx.vstack(
                # Header
                rx.text(
                    "Poseidon Toolkit",
                    size="8",
                    weight="bold",
                    color=rx.color("blue", 11),
                    text_align="center",
                    margin_bottom="0.5rem",
                ),
                rx.text(
                    "Create Super Admin Account",
                    size="5",
                    color=rx.color("slate", 11),
                    text_align="center",
                    margin_bottom="0.5rem",
                ),
                rx.text(
                    "🔐 Super Admin registration requires the master key",
                    size="3",
                    color=rx.color("red", 11),
                    text_align="center",
                    margin_bottom="2rem",
                    font_style="italic",
                ),
                # Super admin registration form
                rx.form(
                    rx.vstack(
                        rx.input(
                            placeholder="Username",
                            name="username",
                            required=True,
                            class_name="w-full p-2 text-sm rounded-md bg-transparent border border-gray-500/40 focus:outline-none focus:border-blue-500 shadow-sm",
                        ),
                        rx.input(
                            placeholder="Email address",
                            name="email",
                            type="email",
                            required=True,
                            class_name="w-full p-2 text-sm rounded-md bg-transparent border border-gray-500/40 focus:outline-none focus:border-blue-500 shadow-sm",
                        ),
                        rx.input(
                            placeholder="Password",
                            name="password",
                            type="password",
                            required=True,
                            class_name="w-full p-2 text-sm rounded-md bg-transparent border border-gray-500/40 focus:outline-none focus:border-blue-500 shadow-sm",
                        ),
                        rx.input(
                            placeholder="Super Admin Master Key",
                            name="super_admin_key",
                            type="password",
                            required=True,
                            class_name="w-full p-2 text-sm rounded-md bg-transparent border border-gray-500/40 focus:outline-none focus:border-blue-500 shadow-sm",
                        ),
                        danger_action_button(
                            text="Create Super Admin Account",
                            icon="🔐",
                            width="100%",
                        ),
                        rx.cond(
                            AuthState.error,
                            error_message(AuthState.error),
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    on_submit=AuthState.register_super_admin,
                    width="100%",
                ),
                # Navigation links
                rx.vstack(
                    rx.box(
                        rx.text(
                            "Need regular account? ",
                            color=rx.color("slate", 11),
                            display="inline",
                        ),
                        rx.link(
                            "User Registration",
                            href="/register",
                            color=rx.color("blue", 11),
                            weight="medium",
                        ),
                        text_align="center",
                    ),
                    rx.box(
                        rx.text(
                            "Already have an account? ",
                            color=rx.color("slate", 11),
                            display="inline",
                        ),
                        rx.link(
                            "Sign in",
                            href="/login",
                            color=rx.color("blue", 11),
                            weight="medium",
                        ),
                        text_align="center",
                    ),
                    spacing="2",
                ),
                spacing="6",
                width="100%",
                max_width="400px",
            ),
            padding="2rem",
            background=rx.color("gray", 2),
            border_radius="12px",
            border=f"1px solid {rx.color('gray', 6)}",
            max_width="450px",
            width="100%",
        ),
        max_width="500px"
    )


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
        on_mount=AuthState.load_available_organizations,
    )


def register_admin_page() -> rx.Component:
    """
    Admin registration page with dynamic rendering.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.cond(
        AuthState.is_authenticated,
        redirect_component("Redirecting to dashboard..."),
        register_admin_content(),
    )


def register_super_admin_page() -> rx.Component:
    """
    Super admin registration page with dynamic rendering.
    Uses unified redirect and form layout components for consistency.
    """
    return rx.cond(
        AuthState.is_authenticated,
        redirect_component("Redirecting to dashboard..."),
        register_super_admin_content(),
    ) 