import reflex as rx

from inspectra.state.auth_state import AuthState
from inspectra.styles.global_styles import T


def _left_panel() -> rx.Component:
    """Left side with form."""
    return rx.box(
        rx.vstack(
            rx.image(src="/Inspectra.svg", height="120px", width="auto"),
            rx.text("THE HOME OF BRAIN-INSPIRED AI", weight="bold", size="3", color=T.primary),
            rx.text("Please log in to your account", color="#475569"),
            rx.form(
                rx.vstack(
                    rx.input(name="username", placeholder="Username", required=True),
                    rx.input(name="password", placeholder="Password", type="password", required=True),
                    rx.button("Login", type="submit", width="100%", bg=T.primary, color="white"),
                    rx.text(AuthState.error, color="red"),
                ),
                on_submit=AuthState.login,
            ),
            rx.link("Forgot password?", href="/forgot-password", color=T.primary_light, margin_top="8px"),
            spacing="4",
            align="center",
            width="100%",
        ),
        padding=T.space_6,
        bg=T.surface,
        height="100%",
    )


def _right_panel() -> rx.Component:
    """Right marketing gradient panel."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("brain-circuit", size=26, color="white"),
                rx.text("mindtrace.ai", weight="bold", size="5", color="white"),
                align="center",
                spacing="3",
            ),
            rx.text(
                "The intelligence layer that turns inspection data into insight",
                weight="medium",
                color="rgba(255,255,255,0.9)",
                size="3",
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        color="white",
        padding="48px",
        background=f"linear-gradient(135deg, {T.primary_light} 0%, {T.primary} 100%)",
        height="100%",
        display="flex",
        align_items="center",
    )


def login() -> rx.Component:
    """Full login page layout."""
    return rx.center(
        rx.box(
            rx.grid(
                _left_panel(),
                _right_panel(),
                columns="repeat(auto-fit, minmax(380px, 1fr))",
                width="100%",
                height="100%",
            ),
            width="min(1080px, 96vw)",
            min_height="560px",
            border_radius="16px",
            overflow="hidden",
            bg=T.surface,
            box_shadow="0 12px 36px rgba(2,6,23,.1)",
        ),
        width="100%",
        min_height="100vh",
        padding="24px",
        bg=T.background,
    )
