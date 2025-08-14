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
    access_denied_component,
    add_organization_popup,
    authentication_required_component,
    filter_bar,
    organization_management_table,
    success_message,
)
from poseidon.components_v2.alerts import Alert
from poseidon.components_v2.containers.page_container import page_container
from poseidon.components_v2.core.button import button
from poseidon.state.auth import AuthState
from poseidon.state.organization_management import OrganizationManagementState


def organization_management_content() -> rx.Component:
    """
    Organization management dashboard content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return page_container(
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
            Alert.create(
                severity="error",
                title="Error",
                message=OrganizationManagementState.error,
            ),
        ),
        # Organization management table using unified component
        organization_management_table(),
        title="Organization Management",
        description="Manage all organizations across the system",
        tools=[
            button(
                text="Refresh",
                icon=rx.icon("refresh-ccw"),
                on_click=OrganizationManagementState.load_organizations,
                loading=OrganizationManagementState.loading,
                variant="secondary",
                size="sm",
            ),
            add_organization_popup(),
        ],
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
