"""Poseidon Form Components - Buridan UI Styling.

Renamed Buridan UI pantry forms for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx
from poseidon.state.auth import AuthState
from .mindtrace_forms import (
    input_with_label_mindtrace,
    input_with_hint_mindtrace,
    select_mindtrace,
    button_mindtrace,
)


def form_input_with_label(label: str, placeholder: str, input_type: str = "text", name: str = "", required: bool = False, size: str = "large"):
    """Form input with label - using mindtrace styling. Supports size variants: small, medium, large (default)."""
    return input_with_label_mindtrace(
        label=label,
        placeholder=placeholder,
        name=name,
        input_type=input_type,
        required=required,
        size=size,
    )


def form_input_with_label_and_hint(label: str, placeholder: str, hint: str, input_type: str = "text", name: str = "", required: bool = False, size: str = "large"):
    """Form input with label and hint - using mindtrace styling. Supports size variants: small, medium, large (default)."""
    return input_with_hint_mindtrace(
        label=label,
        placeholder=placeholder,
        hint=hint,
        input_type=input_type,
        name=name,
        required=required,
        size=size,
    )


def login_form(title: str = "Sign in to your account", subtitle: str = "Enter your credentials"):
    """Login form - keeps Buridan UI styling."""
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold"),
            rx.text(
                subtitle,
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.form(
            rx.vstack(
                form_input_with_label("Email", "example@company.com", "email", "email", True, "medium"),
                form_input_with_label("Password", "Enter your password", "password", "password", True, "medium"),
                modern_button("Sign In", "submit", "medium"),
                # Error display
                rx.cond(
                    AuthState.error,
                    rx.text(
                        AuthState.error,
                        color="red",
                        font_size="12px",
                        text_align="center",
                    )
                ),
                width="100%",
                spacing="3",
            ),
            on_submit=AuthState.login,
            width="100%",
        ),
        width="100%",
        # max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )


def registration_form(title: str = "Create your account", subtitle: str = "Fill out the form to get started", extra_fields=None, submit_label="Create Account", on_submit=AuthState.register):
    """Registration form - keeps Buridan UI styling."""
    if extra_fields is None:
        extra_fields = []
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold"),
            rx.text(
                subtitle,
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.form(
            rx.vstack(
                rx.hstack(
                    form_input_with_label("First Name", "First name"),
                    form_input_with_label("Last Name", "Last name"),
                    width="100%",
                    display="flex",
                ),
                form_input_with_label("Email", "you@company.com", "email", "email", True, "medium"),
                form_input_with_label("Password", "Create password", "password", "password", True, "medium"),
                # Organization selection
                rx.cond(
                    AuthState.organizations_loaded,
                    modern_select_field(
                        "Organization",
                        "Select your organization",
                        AuthState.available_organizations,
                        "organization_id",
                        True,
                        "medium"
                    ),
                    rx.vstack(
                        rx.el.label(
                            "Organization",
                            style={
                                "font_size": "0.875rem",
                                "font_weight": "500",
                                "color": "rgb(71, 85, 105)",
                                "margin_bottom": "0.5rem",
                                "display": "block",
                                "font_family": '"Inter", system-ui, sans-serif',
                            }
                        ),
                        rx.el.input(
                            placeholder="Loading organizations...",
                            disabled=True,
                            style={
                                "width": "100%",
                                "padding": "1rem 1.25rem",
                                "font_size": "0.95rem",
                                "font_family": '"Inter", system-ui, sans-serif',
                                "border_radius": "12px",
                                "background": "rgba(243, 244, 246, 0.8)",
                                "border": "2px solid rgba(226, 232, 240, 0.6)",
                                "outline": "none",
                                "color": "rgb(107, 114, 128)",
                                "cursor": "not-allowed",
                                "backdrop_filter": "blur(10px)",
                            }
                        ),
                        width="100%",
                        spacing="1",
                        style={
                            "margin_bottom": "1rem",
                        }
                    ),
                ),
                # Inject extra fields here (e.g., admin key input)
                *extra_fields,
                modern_button(submit_label, "submit", "medium"),
                # Error display
                rx.cond(
                    AuthState.error,
                    rx.text(
                        AuthState.error,
                        color="red",
                        font_size="12px",
                        text_align="center",
                    )
                ),
                width="100%",
                spacing="1",
            ),
            on_submit=on_submit,
            width="100%",
        ),
        width="100%",
        # max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )


def contact_form(title: str = "Contact us", subtitle: str = "We'd love to hear from you"):
    """Contact form - keeps Buridan UI styling."""
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold"),
            rx.text(
                subtitle,
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.hstack(
            form_input_with_label("First Name", "First name"),
            form_input_with_label("Last Name", "Last name"),
            width="100%",
            display="flex",
        ),
        form_input_with_label("Email", "example@company.com", "email"),
        rx.vstack(
            rx.text("Message", font_size="11px", color_scheme="gray", weight="medium"),
            rx.text_area(
                width="100%",
                placeholder="Tell us how we can help...",
                rows="5",
            ),
            width="100%",
            spacing="2",
        ),
        rx.button(
            "Send Message",
            width="100%",
            cursor="pointer",
            variant="surface",
            color_scheme="gray",
        ),
        width="100%",
        max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )





def modern_select_field(label: str, placeholder: str, options, name: str = "", required: bool = False, size: str = "large"):
    """Modern select field - using mindtrace styling. Supports size variants: small, medium, large (default)."""
    return select_mindtrace(
        label=label,
        placeholder=placeholder,
        options=options,
        name=name,
        required=required,
        size=size,
    )


def modern_button(text: str, button_type: str = "submit", size: str = "large", **kwargs):
    """Modern button - using mindtrace styling. Supports size variants: small, medium, large (default)."""
    return button_mindtrace(
        text=text,
        button_type=button_type,
        size=size,
        **kwargs
    )
