"""Access denied component for unauthorized access."""

import reflex as rx
from reflex_app.styles import COLORS, TYPOGRAPHY, SIZING, SPACING, HEIGHTS, button_variants

def access_denied(message: str = "Access Denied"):
    """Component to show when access is denied."""
    return rx.center(
        rx.vstack(
            rx.heading(
                "🚫 Access Denied",
                font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                color=COLORS["error"],
            ),
            rx.text(
                message,
                color=COLORS["text_muted"],
                text_align="center",
                font_size=TYPOGRAPHY["font_sizes"]["lg"],
            ),
            rx.hstack(
                rx.link(
                    rx.button("Go to Login", **button_variants["primary"]),
                    href="/login",
                ),
                rx.link(
                    rx.button("Go Home", **button_variants["secondary"]),
                    href="/",
                ),
                spacing=SPACING["md"],
            ),
            spacing=SPACING["lg"],
            align="center",
            max_width=SIZING["max_width_form"],
        ),
        height=HEIGHTS["screen_80"],
        background=COLORS["background"],
    ) 