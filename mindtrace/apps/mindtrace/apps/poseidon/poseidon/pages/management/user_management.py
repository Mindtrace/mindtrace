"""
User Management Dashboard - Organization Admin Only.

Comprehensive user administration interface using unified Poseidon UI components:
- View all organization users with table
- Search and filter functionality
- User management actions
- Role-based access control
"""

import reflex as rx
from poseidon.components import (
    user_management_table,
    add_user_popup,
    page_header_with_actions,
    refresh_button,
    filter_bar,
    success_message,
    access_denied_component,
    authentication_required_component,
    assign_project_popup,
    project_management_popup,
)
from poseidon.components_v2.layout import container
from poseidon.components_v2.alerts import Alert
from poseidon.state.auth import AuthState
from poseidon.state.user_management import UserManagementState


def user_management_content() -> rx.Component:
    """
    User management dashboard content using unified Poseidon UI components.
    All state and event logic is handled in the page/state, not in the components.
    """
    return container(
        # Page header with actions
        page_header_with_actions(
            title=rx.cond(AuthState.is_super_admin, "Global User Management", "User Management"),
            description=rx.cond(
                AuthState.is_super_admin,
                "Manage all users across all organizations",
                "Manage organization users, roles, and project assignments",
            ),
            actions=[
                refresh_button(
                    on_click=UserManagementState.load_organization_users,
                    loading=UserManagementState.loading,
                ),
                rx.cond(AuthState.is_admin & ~AuthState.is_super_admin, add_user_popup(), rx.fragment()),
            ],
        ),
        # Filters and search using unified filter_bar
        filter_bar(
            search_value=UserManagementState.search_query,
            search_on_change=UserManagementState.set_search_query,
            role_value=UserManagementState.role_filter,
            role_on_change=UserManagementState.set_role_filter,
            status_value=UserManagementState.status_filter,
            status_on_change=UserManagementState.set_status_filter,
        ),
        # Success/Error messages using unified components
        rx.cond(
            UserManagementState.success,
            success_message(UserManagementState.success),
        ),
        rx.cond(
            UserManagementState.error,
            Alert.create(
                severity="error",
                title="Error",
                message=UserManagementState.error,
            ),
        ),
        # User management table using unified component
        user_management_table(),
        # Project assignment popup
        assign_project_popup(),
        # Project management popup
        project_management_popup(),
        center=False,
    )


def user_management_page() -> rx.Component:
    """
    User management page with role-based access control.
    Uses unified access control and authentication components.
    """
    return rx.cond(
        AuthState.is_authenticated,
        rx.cond(
            AuthState.is_admin | AuthState.is_super_admin,
            user_management_content(),
            access_denied_component("Admin privileges required to access User Management."),
        ),
        authentication_required_component(),
    )
