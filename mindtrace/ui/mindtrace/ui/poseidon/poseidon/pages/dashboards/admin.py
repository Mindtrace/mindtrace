"""
Admin dashboard page component.

Provides administrative interface with:
- Admin feature cards using unified Poseidon UI components
- Role-based access control (admin/super_admin only)
- Clean layout with sidebar and header
"""

import reflex as rx
from poseidon.components import (
    sidebar, app_header, navigation_action_card, page_header, 
    section_header, page_container, authenticated_page_wrapper, card_grid,
    access_denied_component, authentication_required_component
)
from poseidon.state.auth import AuthState


def admin_content() -> rx.Component:
    """
    Admin dashboard content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return rx.box(
        # Sidebar navigation (fixed position)
        rx.box(
            sidebar(),
            position="fixed",
            left="0",
            top="0",
            width="240px",
            height="100vh",
            z_index="1000",
        ),
        
        # Header (fixed position)
        rx.box(
            app_header(),
            position="fixed",
            top="0",
            left="240px",
            right="0",
            height="60px",
            z_index="999",
        ),
        
        # Main content using page_container
        page_container(
            page_header(
                title="Admin Dashboard",
                description="Organization administration and management tools",
                margin_bottom="2rem",
            ),
            
            rx.center(
                rx.vstack(
                    # User Management Section
                    section_header(
                        title="User Management",
                        subtitle="Manage users, roles, and permissions within your organization",
                    ),
                    # Single User Management card
                    rx.link(
                        navigation_action_card(
                            title="User Management",
                            description="View, add, edit, and manage user accounts",
                            icon="👥",
                        ),
                        href="/user-management",
                        text_decoration="none",
                    ),
                    spacing="6",
                    width="100%",
                    max_width="400px",
                    align="center",
                ),
                width="100%",
            ),
            margin_top="60px",  # Account for header
        ),
        
        width="100%",
        min_height="100vh",
        position="relative",
        
        # Initialize admin data
        on_mount=AuthState.check_auth,
    )


def admin_page() -> rx.Component:
    """
    Admin page with role-based access control.
    Uses unified access control and authentication components.
    """
    return rx.cond(
        AuthState.is_authenticated,
        rx.cond(
            AuthState.is_admin | AuthState.is_super_admin,
            admin_content(),
            access_denied_component("Admin privileges required to access the Admin Dashboard."),
        ),
        authentication_required_component(),
    ) 