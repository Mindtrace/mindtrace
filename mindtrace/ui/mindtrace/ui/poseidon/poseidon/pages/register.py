"""Modern registration page component.

Provides user account creation interface with:
- Clean, modern form design
- Username, email, and password input fields
- Role selection for user/admin access levels
- Form validation and error handling
- Responsive design using modern design system
- Consistent with dashboard template styling
"""

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.components.navbar import navbar
from poseidon.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, SHADOWS,
    button_variants, input_variants, card_variants
)


def register_content() -> rx.Component:
    """Modern registration form content for unauthenticated users."""
    return rx.center(
        rx.box(
            rx.vstack(
                # Logo/Brand
                rx.text(
                    "Poseidon Toolkit",
                    font_size=TYPOGRAPHY["font_sizes"]["3xl"],
                    font_weight=TYPOGRAPHY["font_weights"]["bold"],
                    color=COLORS["primary"],
                    text_align="center",
                    margin_bottom=SPACING["sm"],
                ),
                rx.text(
                    "Create your account",
                    font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    color=COLORS["text_muted"],
                    text_align="center",
                    margin_bottom=SPACING["xl"],
                ),
                
                # Registration form
                rx.form(
                    rx.vstack(
                        rx.input(
                            placeholder="Username", 
                            name="username", 
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.input(
                            placeholder="Email address", 
                            name="email", 
                            type="email",
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.input(
                            placeholder="Password", 
                            name="password", 
                            type="password", 
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.select(
                            ["user", "admin"],
                            placeholder="Select Role",
                            name="role",
                            width="100%",
                            default_value="user",
                        ),
                        rx.input(
                            placeholder="Project (optional)", 
                            name="project", 
                            **input_variants["default"]
                        ),
                        rx.input(
                            placeholder="Organization (optional)", 
                            name="organization", 
                            **input_variants["default"]
                        ),
                        rx.button(
                            "Create Account", 
                            width="100%",
                            **button_variants["primary"]
                        ),
                        rx.cond(
                            AuthState.error,
                            rx.text(
                                AuthState.error, 
                                color=COLORS["error"],
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                text_align="center",
                                padding=SPACING["sm"],
                                background=f"{COLORS['error']}10",
                                border_radius=SIZING["border_radius"],
                                border=f"{SIZING['border_width']} solid {COLORS['error']}",
                            )
                        ),
                        spacing=SPACING["md"],
                        width="100%",
                    ),
                    on_submit=AuthState.register,
                    width="100%",
                ),
                
                # Login link
                rx.box(
                    rx.text(
                        "Already have an account? ",
                        color=COLORS["text_muted"],
                        display="inline",
                    ),
                    rx.link(
                        "Sign in",
                        href="/login",
                        color=COLORS["primary"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        _hover={"text_decoration": "underline"},
                    ),
                    text_align="center",
                ),
                
                spacing=SPACING["lg"],
                width="100%",
                max_width="400px",
            ),
            **card_variants["default"],
            max_width="450px",
            width="100%",
        ),
        min_height="100vh",
        background=COLORS["surface"],
        padding=SPACING["lg"],
    )

def register_page() -> rx.Component:
    """Registration page with dynamic rendering - redirects authenticated users."""
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_authenticated),
            register_content(),
        )
    ) 