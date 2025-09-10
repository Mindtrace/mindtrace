import reflex as rx

from poseidon.components_v2.core.button import button
from .modern_select_field import modern_select_field
from .form_input_with_label import form_input_with_label
from .modern_button import modern_button
from poseidon.state.auth import AuthState

def registration_form(
    title: str = "Create your account",
    subtitle: str = "Fill out the form to get started",
    extra_fields=None,
    submit_label="Create Account",
    on_submit=AuthState.register,
):
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
                    form_input_with_label("First Name", "Enter first name", "text", "first_name", True, "medium"),
                    form_input_with_label("Last Name", "Enter last name", "text", "last_name", True, "medium"),
                    width="100%",
                    spacing="4",
                ),
                form_input_with_label("Email", "you@company.com", "email", "email", True, "medium"),
                form_input_with_label("Password", "Create password", "password", "password", True, "medium"),
                form_input_with_label("Confirm Password", "Confirm password", "password", "confirm_password", True, "medium"),
                # Organization selection
                rx.cond(
                    ~AuthState.is_register_super_admin,
                    rx.cond(
                        AuthState.organizations_loaded,
                        modern_select_field(
                            "Organization",
                            "Select your organization",
                            AuthState.available_organizations,
                            "organization_id",
                            True,
                            "medium",
                        ),
                    ),
                ),

                rx.hstack(
                    rx.text("Register as Super Admin", font_size="14px", font_weight="500"),
                    rx.checkbox(
                        checked=AuthState.is_register_super_admin,
                        on_change=AuthState.set_is_register_super_admin,
                        size="3",
                    ),
                    width="100%",
                    spacing="4",
                ),
                rx.cond(
                    AuthState.is_register_super_admin,
                    form_input_with_label(
                        "Super Admin Key",
                        "Enter the super admin key",
                        "password",
                        "super_admin_key",
                        True,
                        "medium",
                    ),
                ),
                *extra_fields,
                modern_button(submit_label, "submit", "md"),
                rx.cond(
                    AuthState.error,
                    rx.text(
                        AuthState.error,
                        color="red",
                        font_size="12px",
                        text_align="center",
                    ),
                ),
                width="100%",
                spacing="1",
            ),
            on_submit=on_submit,
            width="100%",
        ),
        width="100%",
        height="100%",
        justify="center",
        align="center",
    )
