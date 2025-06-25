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
                    "Admin Dashboard",
                    **content_variants["page_title"]
                ),
                rx.text(
                    "Organization management, user administration, and system configuration",
                    **content_variants["page_subtitle"]
                ),
                **content_variants["page_header"]
            ),
            
            # Admin cards grid
            rx.box(
                # User Management card
                rx.link(
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
                                "Manage user accounts, roles, and project assignments",
                                color=COLORS["text_muted"],
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                text_align="center",
                            ),
                            rx.text(
                                "Manage Users →",
                                color=COLORS["primary"],
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                            ),
                            spacing="3",
                            align="center",
                        ),
                        **card_variants["feature"],
                    ),
                    href="/user-management",
                    text_decoration="none",
                ),
                
                # Organization Settings card
                rx.box(
                    rx.vstack(
                        rx.text("🏢", font_size=TYPOGRAPHY["font_sizes"]["4xl"]),
                        rx.heading(
                            "Organization Settings",
                            font_size=TYPOGRAPHY["font_sizes"]["xl"],
                            font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                            color=COLORS["text"],
                        ),
                        rx.text(
                            "Configure organization preferences and limits",
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            text_align="center",
                        ),
                        rx.text(
                            "Configure →",
                            color=COLORS["primary"],
                            font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        ),
                        spacing="3",
                        align="center",
                    ),
                    **card_variants["feature"],
                ),
                
                # Project Management card
                rx.box(
                    rx.vstack(
                        rx.text("📋", font_size=TYPOGRAPHY["font_sizes"]["4xl"]),
                        rx.heading(
                            "Project Management",
                            font_size=TYPOGRAPHY["font_sizes"]["xl"],
                            font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                            color=COLORS["text"],
                        ),
                        rx.text(
                            "Create and manage inspection projects",
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            text_align="center",
                        ),
                        rx.text(
                            "Manage Projects →",
                            color=COLORS["primary"],
                            font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        ),
                        spacing="3",
                        align="center",
                    ),
                    **card_variants["feature"],
                ),
                
                # Analytics card
                rx.box(
                    rx.vstack(
                        rx.text("📊", font_size=TYPOGRAPHY["font_sizes"]["4xl"]),
                        rx.heading(
                            "Analytics & Reports",
                            font_size=TYPOGRAPHY["font_sizes"]["xl"],
                            font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                            color=COLORS["text"],
                        ),
                        rx.text(
                            "View system usage and performance metrics",
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            text_align="center",
                        ),
                        rx.text(
                            "View Reports →",
                            color=COLORS["primary"],
                            font_weight=TYPOGRAPHY["font_weights"]["medium"],
                        ),
                        spacing="3",
                        align="center",
                    ),
                    **card_variants["feature"],
                ),
                
                display="grid",
                grid_template_columns="repeat(auto-fit, minmax(300px, 1fr))",
                gap=SPACING["xl"],
                margin_bottom=SPACING["2xl"],
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
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "Admin:",
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                color=COLORS["text"],
                                min_width="120px",
                            ),
                            rx.text(
                                AuthState.user_display_name,
                                color=COLORS["text_muted"],
                            ),
                            spacing="4",
                            align="center",
                        ),
                        rx.hstack(
                            rx.text(
                                "Organization:",
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                color=COLORS["text"],
                                min_width="120px",
                            ),
                            rx.text(
                                AuthState.user_organization_id,
                                color=COLORS["text_muted"],
                                font_family="monospace",
                            ),
                            spacing="4",
                            align="center",
                        ),
                        rx.hstack(
                            rx.text(
                                "Roles:",
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                color=COLORS["text"],
                                min_width="120px",
                            ),
                            rx.foreach(
                                AuthState.user_org_roles,
                                lambda role: rx.text(
                                    role,
                                    padding="2px 6px",
                                    background=COLORS["primary"],
                                    color="white",
                                    border_radius=SIZING["border_radius"],
                                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                                    font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                    margin="1px",
                                    display="inline-block",
                                ),
                            ),
                            spacing="4",
                            align="center",
                        ),
                        spacing="3",
                        align="stretch",
                        width="100%",
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