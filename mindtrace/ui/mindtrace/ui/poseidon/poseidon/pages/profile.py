"""Modern user profile page - requires authentication."""

import reflex as rx
from poseidon.components.navbar import sidebar, header
from poseidon.state.auth import AuthState
from poseidon.styles.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING,
    card_variants, content_variants
)

def profile_content():
    """Modern profile page content for authenticated users."""
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
                    "User Profile",
                    **content_variants["page_title"]
                ),
                rx.text(
                    "Manage your account information and permissions",
                    **content_variants["page_subtitle"]
                ),
                **content_variants["page_header"]
            ),
            
            # Profile information card
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Account Information",
                        font_size=TYPOGRAPHY["font_sizes"]["xl"],
                        color=COLORS["text"],
                        margin_bottom=SPACING["lg"],
                    ),
                    
                    # User details
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "Username:",
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                color=COLORS["text"],
                                min_width="120px",
                            ),
                            rx.text(
                                AuthState.current_username,
                                color=COLORS["text_muted"],
                            ),
                            spacing="4",
                            align="center",
                        ),
                        rx.hstack(
                            rx.text(
                                "User ID:",
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                color=COLORS["text"],
                                min_width="120px",
                            ),
                            rx.text(
                                AuthState.user_id,
                                color=COLORS["text_muted"],
                                font_family="monospace",
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            ),
                            spacing="4",
                            align="center",
                        ),
                        rx.hstack(
                            rx.text(
                                "Organization ID:",
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                color=COLORS["text"],
                                min_width="120px",
                            ),
                            rx.text(
                                AuthState.user_organization_id,
                                color=COLORS["text_muted"],
                                font_family="monospace",
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            ),
                            spacing="4",
                            align="center",
                        ),
                        spacing="4",
                        align="stretch",
                        width="100%",
                    ),
                    
                    spacing="6",
                    align="start",
                    width="100%",
                ),
                **card_variants["default"],
                max_width="600px",
                margin_bottom=SPACING["xl"],
            ),
            
            # Organization Roles card
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Organization Roles",
                        font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        color=COLORS["text"],
                        margin_bottom=SPACING["md"],
                    ),
                    rx.cond(
                        AuthState.user_org_roles,
                        rx.foreach(
                            AuthState.user_org_roles,
                            lambda role: rx.text(
                                role,
                                padding="4px 8px",
                                background=rx.cond(role == "org_admin", COLORS["primary"], COLORS["text_muted"]),
                                color="white",
                                border_radius=SIZING["border_radius"],
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                                margin="2px",
                            ),
                        ),
                        rx.text(
                            "No organization roles assigned",
                            color=COLORS["text_muted"],
                            font_style="italic",
                        ),
                    ),
                    spacing="4",
                    align="start",
                    width="100%",
                ),
                **card_variants["default"],
                max_width="600px",
                margin_bottom=SPACING["xl"],
            ),
            
            # Project Assignments card
            rx.box(
                rx.vstack(
                    rx.heading(
                        "Project Assignments",
                        font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        color=COLORS["text"],
                        margin_bottom=SPACING["md"],
                    ),
                    rx.cond(
                        AuthState.has_projects,
                        rx.foreach(
                            AuthState.project_assignments_display,
                            lambda assignment_text: rx.box(
                                rx.text(
                                    assignment_text,
                                    color=COLORS["text"],
                                    font_family="monospace",
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                padding=SPACING["md"],
                                border=f"{SIZING['border_width']} solid {COLORS['border']}",
                                border_radius=SIZING["border_radius"],
                                background=COLORS["surface"],
                                margin_bottom="3",
                            ),
                        ),
                        rx.text(
                            "No project assignments",
                            color=COLORS["text_muted"],
                            font_style="italic",
                        ),
                    ),
                    spacing="4",
                    align="start",
                    width="100%",
                ),
                **card_variants["default"],
                max_width="600px",
            ),
            
            **content_variants["container"]
        ),
    )

def profile_page():
    """Profile page with dynamic rendering - redirects unauthenticated users."""
    return rx.box(
        rx.cond(
            AuthState.is_authenticated,
            profile_content(),
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_authenticated),
        )
    ) 