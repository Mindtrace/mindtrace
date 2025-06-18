"""Admin dashboard page - requires admin role."""

import reflex as rx
from reflex_app.components.navbar import navbar
from reflex_app.components.access_denied import access_denied
from reflex_app.state.auth import AuthState
from reflex_app.styles import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING, SPACING, HEIGHTS

def admin_content():
    """Admin dashboard content for admin users."""
    return rx.vstack(
        navbar(active="/admin"),
        rx.center(
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Admin Dashboard",
                        font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                        color=COLORS["primary"],
                    ),
                    rx.text(
                        "Welcome to the admin panel. You have administrative privileges.",
                        color=COLORS["text_muted"],
                        text_align="center",
                    ),
                    rx.box(
                        rx.vstack(
                            rx.heading("Admin Tools", font_size=TYPOGRAPHY["font_sizes"]["2xl"], color=COLORS["text"]),
                            rx.text("• Manage users and permissions"),
                            rx.text("• View system analytics"),
                            rx.text("• Configure application settings"),
                            rx.text("• Monitor system health"),
                            spacing=SPACING["md"],
                            align="start",
                        ),
                        padding=CSS_SPACING["xl"],
                        background=COLORS["surface"],
                        border_radius=SIZING["border_radius"],
                    ),
                    rx.text(
                        f"Logged in as: {AuthState.current_username} (Admin)",
                        color=COLORS["text_muted"],
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    ),
                    spacing=SPACING["lg"],
                    align="center",
                    max_width=SIZING["max_width_content"],
                ),
                padding=CSS_SPACING["2xl"],
                background=COLORS["surface"],
                border=f"{SIZING['border_width']} solid {COLORS['border']}",
                border_radius=SIZING["border_radius"],
            ),
        ),
        spacing=SPACING["lg"],
        background=COLORS["background"],
        min_height=HEIGHTS["screen_full"],
    )

def admin_page():
    """Admin page with role-based access control."""
    return rx.cond(
        AuthState.is_admin(),
        admin_content(),
        rx.cond(
            AuthState.is_authenticated,
            access_denied("Admin privileges required to access this page."),
            access_denied("You must be logged in as an admin to access this page."),
        ),
    ) 