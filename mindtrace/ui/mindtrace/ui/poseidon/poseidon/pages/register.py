"""Modern registration page component.

Provides user account creation interface with:
- Clean, modern form design
- Username, email, and password input fields
- Organization selection (required for multi-tenancy)
- Organization role selection
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
                        rx.cond(
                            AuthState.organizations_loaded,
                            rx.select.root(
                                rx.select.trigger(
                                    placeholder="Select Organization",
                                    width="100%",
                                ),
                                rx.select.content(
                                    rx.foreach(
                                        AuthState.available_organizations,
                                        lambda org: rx.select.item(
                                            org["name"],
                                            value=rx.cond(
                                                org["id"],
                                                org["id"],
                                                "fallback-id"
                                            )
                                        )
                                    ),
                                ),
                                name="organization_id",
                                required=True,
                                width="100%",
                            ),
                            rx.input(
                                placeholder="Loading organizations...", 
                                disabled=True,
                                **input_variants["default"]
                            ),
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
                
                # Admin registration option
                rx.box(
                    rx.text(
                        "Need to create an Organization Admin? ",
                        color=COLORS["text_muted"],
                        display="inline",
                    ),
                    rx.link(
                        "Admin Registration",
                        href="/register-admin",
                        color=COLORS["primary"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        _hover={"text_decoration": "underline"},
                    ),
                    text_align="center",
                    margin_bottom=SPACING["sm"],
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

def register_admin_content() -> rx.Component:
    """Admin registration form content."""
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
                    "Create Organization Admin Account",
                    font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    color=COLORS["text_muted"],
                    text_align="center",
                    margin_bottom=SPACING["sm"],
                ),
                rx.text(
                    "⚠️ Admin registration requires a special key for security",
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    color=COLORS["warning"],
                    text_align="center",
                    margin_bottom=SPACING["xl"],
                    font_style="italic",
                ),
                
                # Admin registration form
                rx.form(
                    rx.vstack(
                        rx.input(
                            placeholder="Admin Username", 
                            name="username", 
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.input(
                            placeholder="Admin Email", 
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
                        rx.cond(
                            AuthState.organizations_loaded,
                            rx.select.root(
                                rx.select.trigger(
                                    placeholder="Select Organization",
                                    width="100%",
                                ),
                                rx.select.content(
                                    rx.foreach(
                                        AuthState.available_organizations,
                                        lambda org: rx.select.item(
                                            org["name"],
                                            value=rx.cond(
                                                org["id"],
                                                org["id"],
                                                "fallback-id"
                                            )
                                        )
                                    ),
                                ),
                                name="organization_id",
                                required=True,
                                width="100%",
                            ),
                            rx.input(
                                placeholder="Loading organizations...", 
                                disabled=True,
                                **input_variants["default"]
                            ),
                        ),
                        rx.input(
                            placeholder="Admin Registration Key (required)", 
                            name="admin_key", 
                            type="password",
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.button(
                            "Create Admin Account", 
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
                    on_submit=AuthState.register_admin,
                    width="100%",
                ),
                
                # Back to regular registration
                rx.box(
                    rx.link(
                        "← Back to regular registration",
                        href="/register",
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

def register_super_admin_content() -> rx.Component:
    """Super admin registration form content."""
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
                    "Create Super Admin Account",
                    font_size=TYPOGRAPHY["font_sizes"]["xl"],
                    color=COLORS["text"],
                    text_align="center",
                    margin_bottom=SPACING["sm"],
                ),
                rx.text(
                    "🔐 First-time system setup only",
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    color=COLORS["error"],
                    text_align="center",
                    margin_bottom=SPACING["xl"],
                    font_style="italic",
                    font_weight=TYPOGRAPHY["font_weights"]["bold"],
                ),
                
                # Super admin registration form
                rx.form(
                    rx.vstack(
                        rx.input(
                            placeholder="Super Admin Username", 
                            name="username", 
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.input(
                            placeholder="Super Admin Email", 
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
                        rx.input(
                            placeholder="Super Admin Key (required)", 
                            name="super_admin_key", 
                            type="password",
                            required=True,
                            **input_variants["default"]
                        ),
                        rx.button(
                            "Create Super Admin Account", 
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
                    on_submit=AuthState.register_super_admin,
                    width="100%",
                ),
                
                # Back to login
                rx.box(
                    rx.link(
                        "← Back to login",
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
        ),
        on_mount=AuthState.load_available_organizations,
    )

def register_admin_page() -> rx.Component:
    """Admin registration page with dynamic rendering - redirects authenticated users."""
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_authenticated),
            register_admin_content(),
        ),
        on_mount=AuthState.load_available_organizations,
    )

def register_super_admin_page() -> rx.Component:
    """Super admin registration page - only for initial system setup."""
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_authenticated),
            register_super_admin_content(),
        )
    ) 