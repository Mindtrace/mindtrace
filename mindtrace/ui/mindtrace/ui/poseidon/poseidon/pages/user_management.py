"""User Management Dashboard - Organization Admin Only.

Comprehensive user administration interface including:
- View all organization users
- Assign users to projects with roles
- Update user organization roles
- Activate/deactivate user accounts
- Search and filter users
- User permission management
"""

import reflex as rx
from poseidon.components.navbar import sidebar, header
from poseidon.state.auth import AuthState
from poseidon.state.user_management import UserManagementState
from poseidon.styles.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING,
    card_variants, content_variants, button_variants, input_variants
)

def user_card(user) -> rx.Component:
    """Create a user card component."""
    return rx.box(
        rx.vstack(
            # User header
            rx.hstack(
                rx.vstack(
                    rx.heading(
                        user["username"],
                        font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        color=COLORS["text"],
                        margin_bottom="0",
                    ),
                    rx.text(
                        user["email"],
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                        color=COLORS["text_muted"],
                        margin_bottom="0",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.text(
                    rx.cond(user["is_active"], "Active", "Inactive"),
                    padding="2px 6px",
                    background=rx.cond(user["is_active"], COLORS["success"], COLORS["error"]),
                    color="white",
                    border_radius=SIZING["border_radius"],
                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                    font_weight=TYPOGRAPHY["font_weights"]["medium"],
                ),
                spacing="4",
                align="start",
                width="100%",
            ),
            
            # User info
            rx.text(
                f"User ID: {user['id']}",
                font_size=TYPOGRAPHY["font_sizes"]["xs"],
                color=COLORS["text_muted"],
                font_family="monospace",
            ),
            
            # Action buttons
            rx.hstack(
                rx.button(
                    "Edit User",
                    size="2",
                    **button_variants["secondary"]
                ),
                rx.cond(
                    user["is_active"],
                    rx.button(
                        "Deactivate",
                        size="2",
                        **button_variants["danger"],
                        on_click=UserManagementState.deactivate_user(user["id"]),
                    ),
                    rx.button(
                        "Activate",
                        size="2",
                        **button_variants["success"],
                        on_click=UserManagementState.activate_user(user["id"]),
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            
            spacing="4",
            align="start",
            width="100%",
        ),
        **card_variants["default"],
        margin_bottom=SPACING["md"],
    )

def user_management_content():
    """User management dashboard content."""
    return rx.fragment(
        # Sidebar navigation
        sidebar(),
        
        # Header
        header(),
        
        # Main content area
        rx.box(
            # Page header
            rx.box(
                rx.hstack(
                    rx.vstack(
                        rx.heading(
                            "User Management",
                            **content_variants["page_title"]
                        ),
                        rx.text(
                            "Manage organization users, roles, and project assignments",
                            **content_variants["page_subtitle"]
                        ),
                        spacing="2",
                        align="start",
                    ),
                    rx.spacer(),
                    rx.button(
                        "Refresh Users",
                        on_click=UserManagementState.load_organization_users,
                        loading=UserManagementState.loading,
                        **button_variants["primary"]
                    ),
                    spacing="4",
                    align="center",
                    width="100%",
                ),
                **content_variants["page_header"]
            ),
            
            # Filters and search
            rx.box(
                rx.hstack(
                    rx.input(
                        placeholder="Search users by name or email...",
                        value=UserManagementState.search_query,
                        on_change=UserManagementState.set_search_query,
                        **input_variants["default"],
                        max_width="400px",
                    ),
                    rx.select(
                        ["all_roles", "member", "org_admin", "viewer"],
                        placeholder="Filter by role",
                        value=UserManagementState.role_filter,
                        on_change=UserManagementState.set_role_filter,
                        max_width="200px",
                    ),
                    rx.select(
                        ["active", "inactive", "all"],
                        value=UserManagementState.status_filter,
                        on_change=UserManagementState.set_status_filter,
                        max_width="150px",
                    ),
                    spacing="4",
                    align="center",
                    width="100%",
                ),
                **card_variants["default"],
                margin_bottom=SPACING["xl"],
            ),
            
            # Success/Error messages
            rx.cond(
                UserManagementState.success,
                rx.box(
                    rx.text(
                        UserManagementState.success,
                        color=COLORS["success"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                    ),
                    padding=SPACING["md"],
                    background=f"{COLORS['success']}10",
                    border=f"1px solid {COLORS['success']}",
                    border_radius=SIZING["border_radius"],
                    margin_bottom=SPACING["lg"],
                ),
            ),
            rx.cond(
                UserManagementState.error,
                rx.box(
                    rx.text(
                        UserManagementState.error,
                        color=COLORS["error"],
                        font_weight=TYPOGRAPHY["font_weights"]["medium"],
                    ),
                    padding=SPACING["md"],
                    background=f"{COLORS['error']}10",
                    border=f"1px solid {COLORS['error']}",
                    border_radius=SIZING["border_radius"],
                    margin_bottom=SPACING["lg"],
                ),
            ),
            
            # Users grid
            rx.cond(
                UserManagementState.loading,
                rx.center(
                    rx.spinner(size="3"),
                    padding=SPACING["2xl"],
                ),
                rx.cond(
                    UserManagementState.filtered_users,
                    rx.box(
                        # User count
                        rx.text(
                            "Organization users",
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            margin_bottom=SPACING["lg"],
                        ),
                        # Users grid
                        rx.foreach(
                            UserManagementState.filtered_users,
                            user_card,
                        ),
                    ),
                    rx.center(
                        rx.vstack(
                            rx.text(
                                "👥",
                                font_size=TYPOGRAPHY["font_sizes"]["6xl"],
                                color=COLORS["text_muted"],
                            ),
                            rx.text(
                                "No users found",
                                font_size=TYPOGRAPHY["font_sizes"]["lg"],
                                color=COLORS["text_muted"],
                                font_weight=TYPOGRAPHY["font_weights"]["medium"],
                            ),
                            rx.text(
                                "Click 'Refresh Users' to load organization users",
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                color=COLORS["text_muted"],
                            ),
                            spacing="4",
                            align="center",
                        ),
                        padding=SPACING["2xl"],
                    ),
                ),
            ),
            
            **content_variants["container"]
        ),
        
        # Load users on mount
        on_mount=UserManagementState.load_organization_users,
    )

def user_management_page():
    """User management page - requires organization admin role."""
    return rx.box(
        rx.cond(
            AuthState.is_admin,
            user_management_content(),
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_admin),
        )
    ) 