import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.components_v2.core import button
from .form_input_with_label import form_input_with_label
from poseidon.components_v2.alerts import Alert

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
                button(
                  text="Sign In",
                  type="submit",
                  size="md",
                  full_width=True,
                ),
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
