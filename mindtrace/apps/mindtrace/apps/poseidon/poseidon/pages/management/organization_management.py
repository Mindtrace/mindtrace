"""
Organization Management Dashboard - Super Admin Only.

Comprehensive organization administration interface using unified Poseidon UI components:
- View all organizations with table
- Search and filter functionality
- Organization management actions
- Role-based access control for super admin only
"""

import reflex as rx
from poseidon.components import (
    sidebar, app_header, organization_management_table, 
    add_organization_popup, page_header_with_actions,
    refresh_button, filter_bar, success_message, error_message,
    page_container, authenticated_page_wrapper,
    access_denied_component, authentication_required_component
)
from poseidon.state.auth import AuthState
from poseidon.state.organization_management import OrganizationManagementState


def organization_management_content() -> rx.Component:
    """
    Organization management dashboard content using unified Poseidon UI components.
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
            # Page header with actions
            page_header_with_actions(
                title="Organization Management",
                description="Manage all organizations across the system",
                actions=[
                    refresh_button(
                        on_click=OrganizationManagementState.load_organizations,
                        loading=OrganizationManagementState.loading,
                    ),
                    add_organization_popup(),
                ],
            ),
            
            # Filters and search using unified filter_bar
            filter_bar(
                search_value=OrganizationManagementState.search_query,
                search_on_change=OrganizationManagementState.set_search_query,
                role_value=OrganizationManagementState.status_filter,
                role_on_change=OrganizationManagementState.set_status_filter,
                status_value=OrganizationManagementState.plan_filter,
                status_on_change=OrganizationManagementState.set_plan_filter,
            ),
            
            # Success/Error messages using unified components
            rx.cond(
                OrganizationManagementState.success,
                success_message(OrganizationManagementState.success),
            ),
            rx.cond(
                OrganizationManagementState.error,
                error_message(OrganizationManagementState.error),
            ),
            
            # Organization management table using unified component
            organization_management_table(),
            
            margin_top="60px",  # Account for header
        ),
        
        width="100%",
        min_height="100vh",
        position="relative",
        
        # Load organizations on mount
        on_mount=OrganizationManagementState.load_organizations,
    )


def organization_management_page() -> rx.Component:
    """
    Organization management page with role-based access control.
    Uses unified access control and authentication components.
    """
    return rx.cond(
        AuthState.is_authenticated,
        rx.cond(
            AuthState.is_super_admin,
            organization_management_content(),
            access_denied_component("Super Admin privileges required to access Organization Management."),
        ),
        authentication_required_component(),
    ) 