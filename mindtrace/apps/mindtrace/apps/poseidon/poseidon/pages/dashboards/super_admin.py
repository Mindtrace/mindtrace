"""
Super Admin Dashboard page.

Provides system-wide management and configuration using unified Poseidon UI components.
- Uses consistent sidebar/header/page_container layout
- Role-based access control (super_admin only)
"""
import reflex as rx
from poseidon.components import sidebar, app_header, navigation_action_card, page_header, section_header, page_container, card_grid, access_denied_component, authentication_required_component
from poseidon.state.auth import AuthState

def super_admin_dashboard_content():
    """
    Super admin dashboard content using unified Poseidon UI components.
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
                title="Super Admin Dashboard",
                description="System-wide management and configuration",
                margin_bottom="2rem",
            ),
            rx.center(
                rx.vstack(
                    section_header(
                        title="System Management",
                        subtitle="Manage users and organizations across all tenants",
                    ),
                    card_grid(
                        rx.link(
                            navigation_action_card(
                                title="User Management",
                                description="Manage users across all organizations",
                                icon="👥",
                            ),
                            href="/user-management",
                            text_decoration="none",
                        ),
                        rx.link(
                            navigation_action_card(
                                title="Organization Management",
                                description="Manage organizations and their settings",
                                icon="🏢",
                            ),
                            href="/organization-management",
                            text_decoration="none",
                        ),
                        min_card_width="320px",
                        max_width="700px",
                        justify_content="center",
                    ),
                    spacing="6",
                    width="100%",
                    max_width="900px",
                    align="center",
                ),
                width="100%",
            ),
            margin_top="60px",  # Account for header
        ),
        width="100%",
        min_height="100vh",
        position="relative",
    )


def super_admin_dashboard_page():
    """
    Super admin dashboard page with role-based access control.
    Uses unified access control and authentication components.
    """
    return rx.cond(
        AuthState.is_authenticated,
        rx.cond(
            AuthState.is_super_admin,
            super_admin_dashboard_content(),
            access_denied_component("Super Admin privileges required to access the Super Admin Dashboard."),
        ),
        authentication_required_component(),
    ) 