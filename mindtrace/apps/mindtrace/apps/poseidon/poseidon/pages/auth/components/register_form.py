import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.components_v2.core import button
from .form_input_with_label import form_input_with_label
from poseidon.components_v2.alerts import Alert
from poseidon.components_v2.core import button
from poseidon.components_v2.forms.select_input import select_input_with_form
from poseidon.state.auth import AuthState

from .form_input_with_label import form_input_with_label


def register_form(
    title: str = "Create your account",
    subtitle: str = "Fill out the form to get started",
    extra_fields=None,
    submit_label="Create Account",
    on_submit=AuthState.register,
):
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
                form_input_with_label("Username", "Enter username", "text", "username", True, "medium"),
                form_input_with_label("Email", "you@company.com", "email", "email", True, "medium"),
                form_input_with_label("Password", "Create password", "password", "password", True, "medium"),
                # Organization selection
                rx.cond(
                    AuthState.organizations_loaded,
                    select_input_with_form(
                        label="Organization",
                        placeholder="Select your organization",
                        items=AuthState.available_organizations,
                        name="organization_id",
                        required=True,
                        size="medium",
                    ),
                ),
                # Inject extra fields here (e.g., admin key input)
                *extra_fields,
                button(submit_label, type="submit", size="md"),
                # Error display
                rx.cond(
                    AuthState.error,
                    rx.box(
                      Alert.create(
                        severity="error",
                        title="Error",
                        message=AuthState.error,
                      ),
                      style={"animation": "shake 0.5s ease-in-out", "width": "100%", "margin_top": "1rem"}
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
