"""Registration page component.

Provides user account creation interface with:
- Username, email, and password input fields
- Role selection for user/admin access levels
- Form validation and error handling
- Responsive design using design system
"""

import reflex as rx
from reflex_app.state.auth import AuthState
from reflex_app.components.navbar import navbar
from reflex_app.styles import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING, SPACING, button_variants, BOX_SHADOWS, WIDTHS, HEIGHTS


def register_page() -> rx.Component:
    """Registration page with account creation form.
    
    Returns:
        Complete registration page with navbar and centered form
    """
    return rx.center(
        rx.vstack(
            navbar(active="/register"),
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Create Account", 
                        font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                        color=COLORS["text"],
                        text_align="center",
                    ),
                    rx.form(
                        rx.vstack(
                            rx.input(
                                placeholder="Username", 
                                name="username", 
                                width=WIDTHS["full"],
                                required=True,
                            ),
                            rx.input(
                                placeholder="Email", 
                                name="email", 
                                width=WIDTHS["full"],
                                type="email",
                                required=True,
                            ),
                            rx.input(
                                placeholder="Password", 
                                name="password", 
                                type="password", 
                                width=WIDTHS["full"],
                                required=True,
                            ),
                            rx.select(
                                ["user", "admin"],
                                placeholder="Select Role",
                                name="role",
                                width=WIDTHS["full"],
                                default_value="user",
                            ),
                            rx.input(
                                placeholder="Project (optional)", 
                                name="project", 
                                width=WIDTHS["full"],
                            ),
                            rx.input(
                                placeholder="Organization (optional)", 
                                name="organization", 
                                width=WIDTHS["full"],
                            ),
                            rx.button(
                                "Create Account", 
                                width=WIDTHS["full"], 
                                **button_variants["primary"]
                            ),
                            rx.cond(
                                AuthState.error,
                                rx.text(
                                    AuthState.error, 
                                    color=COLORS["error"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                    text_align="center",
                                )
                            ),
                            spacing=SPACING["md"],
                            width=WIDTHS["full"],
                        ),
                        on_submit=AuthState.register,
                        width=WIDTHS["full"],
                    ),
                    rx.link(
                        "Already have an account? Login", 
                        href="/login",
                        color=COLORS["primary"],
                        text_align="center",
                    ),
                    spacing=SPACING["lg"],
                    width=WIDTHS["full"],
                    max_width=SIZING["max_width_form"],
                ),
                padding=CSS_SPACING["xl"],
                background=COLORS["surface"],
                border=f"{SIZING['border_width']} solid {COLORS['border']}",
                border_radius=SIZING["border_radius"],
                box_shadow=BOX_SHADOWS["md"],
            ),
            spacing=SPACING["lg"],
        ),
        height=HEIGHTS["screen_full"],
        background=COLORS["background"],
    ) 