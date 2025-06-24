"""Modern admin dashboard page - requires admin role."""

import reflex as rx
from poseidon.components.navbar import sidebar, header
from poseidon.state.auth import AuthState
from poseidon.styles.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING,
    card_variants, content_variants, grid_variants
)

def admin_content():
    """Modern admin dashboard content for admin users."""
    return rx.fragment(
        # Sidebar navigation
        sidebar(),
        
        # Header
        header(),
        
        # Main content area
        rx.box(
            # Page header
            rx.box(
                rx.heading(
                    "Admin & Security",
                    **content_variants["page_title"]
                ),
                rx.text(
                    "User management, system configuration, and audit trails",
                    **content_variants["page_subtitle"]
                ),
                **content_variants["page_header"]
            ),
            
            # User Management card
            rx.box(
                rx.box(
                    rx.vstack(
                        rx.text("👥", font_size=TYPOGRAPHY["font_sizes"]["4xl"]),
                        rx.heading(
                            "User Management",
                            font_size=TYPOGRAPHY["font_sizes"]["xl"],
                            font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                            color=COLORS["text"],
                        ),
                        rx.text(
                            "Manage user accounts, roles, and permissions",
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["sm"],
                        ),
                        rx.link(
                            "Manage Users →",
                            href="#",
                            color=COLORS["primary"],
                            font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        ),
                        spacing="3",
                        align="start",
                    ),
                    **card_variants["feature"]
                ),
                max_width="400px",
                margin_bottom=SPACING["xl"],
            ),
            
            # Admin info section
            rx.box(
                rx.heading(
                    "Administrator Information",
                    font_size=TYPOGRAPHY["font_sizes"]["xl"],
                    color=COLORS["text"],
                    margin_bottom=SPACING["md"],
                ),
                rx.box(
                    rx.text(
                        f"Logged in as: {AuthState.user_display_name}",
                        color=COLORS["text"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                    ),
                    rx.text(
                        f"Role: {AuthState.role_display}",
                        color=COLORS["text_muted"],
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    ),
                    **card_variants["default"]
                ),
            ),
            
            **content_variants["container"]
        ),
    )

def admin_page():
    """Admin page with dynamic rendering - redirects unauthorized users."""
    return rx.box(
        rx.cond(
            AuthState.is_admin,
            admin_content(),
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_admin),
        )
    ) 