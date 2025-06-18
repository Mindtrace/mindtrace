"""User profile page - requires authentication."""

import reflex as rx
from reflex_app.components.navbar import navbar
from reflex_app.components.access_denied import access_denied
from reflex_app.state.auth import AuthState
from reflex_app.styles import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING, SPACING, HEIGHTS

def profile_content():
    """Profile page content for authenticated users."""
    return rx.vstack(
        navbar(active="/profile"),
        rx.center(
            rx.box(
                rx.vstack(
                    rx.heading(
                        "User Profile",
                        font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                        color=COLORS["text"],
                    ),
                    rx.box(
                        rx.vstack(
                            rx.text(
                                f"Username: {AuthState.current_username}",
                                font_size=TYPOGRAPHY["font_sizes"]["lg"],
                            ),
                            rx.text(
                                f"User ID: {AuthState.user_id}",
                                color=COLORS["text_muted"],
                            ),
                            rx.cond(
                                AuthState.user_roles.length() > 0,
                                rx.text(
                                    f"Roles: {AuthState.user_roles.join(', ')}",
                                    color=COLORS["text_muted"],
                                ),
                                rx.text(
                                    "Roles: No roles assigned",
                                    color=COLORS["text_muted"],
                                ),
                            ),
                            rx.cond(
                                AuthState.user_project != "",
                                rx.text(
                                    f"Project: {AuthState.user_project}",
                                    color=COLORS["text_muted"],
                                ),
                                rx.text(
                                    "Project: Not assigned",
                                    color=COLORS["text_muted"],
                                ),
                            ),
                            rx.cond(
                                AuthState.user_organization != "",
                                rx.text(
                                    f"Organization: {AuthState.user_organization}",
                                    color=COLORS["text_muted"],
                                ),
                                rx.text(
                                    "Organization: Not assigned",
                                    color=COLORS["text_muted"],
                                ),
                            ),
                            spacing=SPACING["md"],
                            align="start",
                        ),
                        padding=CSS_SPACING["xl"],
                        background=COLORS["surface"],
                        border_radius=SIZING["border_radius"],
                    ),
                    spacing=SPACING["lg"],
                    align="center",
                    max_width=SIZING["max_width_form"],
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

def profile_page():
    """Profile page with authentication check."""
    return rx.cond(
        AuthState.is_authenticated,
        profile_content(),
        access_denied("You must be logged in to view your profile."),
    ) 