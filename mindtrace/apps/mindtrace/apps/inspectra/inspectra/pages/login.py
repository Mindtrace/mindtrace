import reflex as rx

from inspectra.state.auth_state import AuthState
from inspectra.styles.global_styles import DS


# ──────────────────────────────── Left Panel ────────────────────────────────
def _left_panel() -> rx.Component:
    """Login form panel."""
    return rx.box(
        rx.vstack(
            rx.image(src="/Inspectra.svg", height="120px", width="auto"),
            rx.text(
                "THE HOME OF BRAIN-INSPIRED AI",
                weight="bold",
                size="3",
                color=DS.color.brand,
                letter_spacing="0.05em",
            ),
            rx.text(
                "Please log in to your account",
                color=DS.color.text_secondary,
                size="2",
                margin_bottom=DS.space_px.md,
            ),
            # Login form
            rx.form(
                rx.vstack(
                    rx.input(
                        name="email",
                        placeholder="email",
                        required=True,
                        border=f"1px solid {DS.color.border}",
                        padding=DS.space_px.sm,
                        border_radius=DS.radius.md,
                        width="100%",
                    ),
                    rx.input(
                        name="password",
                        placeholder="Password",
                        type="password",
                        required=True,
                        border=f"1px solid {DS.color.border}",
                        padding=DS.space_px.sm,
                        border_radius=DS.radius.md,
                        width="100%",
                    ),
                    rx.button(
                        "Login",
                        type="submit",
                        width="100%",
                        bg=DS.color.brand,
                        color=DS.color.surface,
                        border_radius=DS.radius.md,
                        padding_y=DS.space_px.sm,
                        _hover={"bg": DS.color.brand_light},
                        transition="all .2s ease",
                    ),
                    rx.text(
                        AuthState.error,
                        color=DS.color.error,
                        size="2",
                        margin_top=DS.space_px.xs,
                    ),
                    spacing=DS.space_token.md,
                    align="stretch",
                    width="100%",
                ),
                on_submit=AuthState.login,
            ),
            rx.link(
                "Forgot password?",
                href="/forgot-password",
                color=DS.color.brand_light,
                margin_top=DS.space_px.sm,
                font_weight="medium",
                text_decoration="none",
                _hover={"text_decoration": "underline"},
            ),
            spacing=DS.space_token.lg,
            align="center",
            width="100%",
        ),
        padding=DS.space_px.lg,
        bg=DS.color.surface,
        height="100%",
    )


# ──────────────────────────────── Right Panel ────────────────────────────────
def _right_panel() -> rx.Component:
    """Marketing/branding side with gradient."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("brain_circuit", size=26, color=DS.color.surface),
                rx.text(
                    "mindtrace.ai",
                    weight="bold",
                    size="5",
                    color=DS.color.surface,
                    letter_spacing="-0.02em",
                ),
                align="center",
                spacing=DS.space_token.sm,
            ),
            rx.text(
                "The intelligence layer that turns inspection data into insight.",
                weight="medium",
                color="rgba(255,255,255,0.9)",
                size="3",
                max_width="360px",
                line_height="1.4",
            ),
            spacing=DS.space_token.lg,
            align="start",
            width="100%",
        ),
        padding=DS.space_px.xl,
        background=f"linear-gradient(135deg, {DS.color.brand_light} 0%, {DS.color.brand} 100%)",
        height="100%",
        display="flex",
        align_items="center",
        color=DS.color.surface,
    )


# ──────────────────────────────── Login Page ────────────────────────────────
def login() -> rx.Component:
    """Full-page login layout."""
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
            border_radius=DS.radius.lg,
            overflow="hidden",
            bg=DS.color.surface,
            box_shadow="0 12px 36px rgba(2,6,23,.1)",
        ),
        width="100%",
        min_height="100vh",
        padding=DS.space_px.lg,
        bg=DS.color.background,
    )
