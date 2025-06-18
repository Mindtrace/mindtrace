"""Login page component.

Provides user authentication interface with:
- Email and password input fields
- Form validation and error handling
- Responsive design using design system
- Navigation integration with auth state
"""

import reflex as rx
from reflex_app.state.auth import AuthState
from reflex_app.components.navbar import navbar
from reflex_app.styles import COLORS, TYPOGRAPHY, CSS_SPACING, SIZING, SPACING, button_variants, BOX_SHADOWS, WIDTHS, HEIGHTS


def login_page() -> rx.Component:
    """Login page with authentication form.
    
    Returns:
        Complete login page with navbar and centered form
    """
    return rx.center(
        rx.vstack(
            navbar(active="/login"),
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Login", 
                        font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                        color=COLORS["text"],
                        text_align="center",
                    ),
                    rx.form(
                        rx.vstack(
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
                            rx.button(
                                "Login", 
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
                        on_submit=AuthState.login,
                        width=WIDTHS["full"],
                    ),
                    rx.link(
                        "Don't have an account? Register", 
                        href="/register",
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