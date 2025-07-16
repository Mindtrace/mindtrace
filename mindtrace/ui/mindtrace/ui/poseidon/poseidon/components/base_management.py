import reflex as rx
from typing import List, Callable, Optional, Any
from .sidebar import sidebar
from .headers import app_header, page_header_with_actions
from .buttons import refresh_button
from .inputs import success_message, error_message, filter_bar
from .layouts import page_container
from .utilities import access_denied_component, authentication_required_component
from poseidon.state.auth import AuthState


def base_management_page(
    title: str,
    description: str,
    state_class: Any,
    content_component: Callable,
    actions: Optional[List[rx.Component]] = None,
    filter_component: Optional[rx.Component] = None,
    required_role: str = "admin",  # "admin", "super_admin", or "user"
    on_mount: Optional[Callable] = None
) -> rx.Component:
    """
    Base management page component with common layout structure.
    
    Args:
        title: Page title
        description: Page description
        state_class: State class for the page
        content_component: Main content component function
        actions: Optional list of action buttons for the header
        filter_component: Optional filter component
        required_role: Required role for access ("admin", "super_admin", "user")
        on_mount: Optional function to call on mount
    """
    
    # Build default actions if none provided
    if actions is None:
        actions = [
            refresh_button(
                on_click=getattr(state_class, 'load_data', lambda: None),
                loading=state_class.loading if hasattr(state_class, 'loading') else False,
            )
        ]
    
    # Build access control condition
    access_condition = None
    if required_role == "super_admin":
        access_condition = AuthState.is_super_admin
        access_denied_msg = "Super Admin privileges required to access this page."
    elif required_role == "admin":
        access_condition = AuthState.is_admin | AuthState.is_super_admin
        access_denied_msg = "Admin privileges required to access this page."
    else:  # user or no specific role
        access_condition = True
        access_denied_msg = "Access denied."
    
    def management_content():
        """Management page content with common layout"""
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
                    title=title,
                    description=description,
                    actions=actions,
                ),
                
                # Optional filter component
                rx.cond(
                    filter_component is not None,
                    filter_component,
                    rx.fragment(),
                ),
                
                # Success/Error messages using unified components
                rx.cond(
                    state_class.success if hasattr(state_class, 'success') else False,
                    success_message(state_class.success if hasattr(state_class, 'success') else ""),
                ),
                rx.cond(
                    state_class.error if hasattr(state_class, 'error') else False,
                    error_message(state_class.error if hasattr(state_class, 'error') else ""),
                ),
                
                # Main content component
                content_component(),
                
                margin_top="60px",  # Account for header
            ),
            
            width="100%",
            min_height="100vh",
            position="relative",
            
            # Optional on_mount handler
            on_mount=on_mount if on_mount else lambda: None,
        )
    
    # Return page with access control
    return rx.cond(
        AuthState.is_authenticated,
        rx.cond(
            access_condition,
            management_content(),
            access_denied_component(access_denied_msg),
        ),
        authentication_required_component(),
    )


def standard_filter_bar(
    state_class: Any,
    show_organization_filter: bool = False,
    show_role_filter: bool = False,
    show_plan_filter: bool = False,
    custom_filters: Optional[List[rx.Component]] = None
) -> rx.Component:
    """
    Standard filter bar component for management pages.
    
    Args:
        state_class: State class containing filter properties
        show_organization_filter: Whether to show organization filter
        show_role_filter: Whether to show role filter
        show_plan_filter: Whether to show plan filter (for organizations)
        custom_filters: Additional custom filter components
    """
    
    filters = [
        # Search input
        rx.input(
            placeholder="Search...",
            value=state_class.search_query if hasattr(state_class, 'search_query') else "",
            on_change=state_class.set_search_query if hasattr(state_class, 'set_search_query') else lambda x: None,
            size="2",
            max_width="300px",
        ),
        
        # Status filter
        rx.select(
            ["active", "inactive", "all"],
            placeholder="Filter by status",
            value=state_class.status_filter if hasattr(state_class, 'status_filter') else "active",
            on_change=state_class.set_status_filter if hasattr(state_class, 'set_status_filter') else lambda x: None,
            size="2",
        ),
    ]
    
    # Add organization filter if requested
    if show_organization_filter:
        filters.append(
            rx.cond(
                AuthState.is_super_admin,
                rx.select(
                    state_class.organization_filter_options if hasattr(state_class, 'organization_filter_options') else ["all"],
                    placeholder="Filter by organization",
                    value=state_class.organization_filter if hasattr(state_class, 'organization_filter') else "",
                    on_change=state_class.set_organization_filter if hasattr(state_class, 'set_organization_filter') else lambda x: None,
                    size="2",
                ),
                rx.fragment(),
            )
        )
    
    # Add role filter if requested
    if show_role_filter:
        filters.append(
            rx.select(
                ["all_roles", "user", "admin"],
                placeholder="Filter by role",
                value=state_class.role_filter if hasattr(state_class, 'role_filter') else "",
                on_change=state_class.set_role_filter if hasattr(state_class, 'set_role_filter') else lambda x: None,
                size="2",
            )
        )
    
    # Add plan filter if requested
    if show_plan_filter:
        filters.append(
            rx.select(
                ["all", "basic", "premium", "enterprise"],
                placeholder="Filter by plan",
                value=state_class.plan_filter if hasattr(state_class, 'plan_filter') else "",
                on_change=state_class.set_plan_filter if hasattr(state_class, 'set_plan_filter') else lambda x: None,
                size="2",
            )
        )
    
    # Add custom filters if provided
    if custom_filters:
        filters.extend(custom_filters)
    
    return rx.box(
        rx.hstack(
            *filters,
            spacing="4",
            align="center",
            width="100%",
        ),
        padding="1rem",
        background=rx.color("gray", 2),
        border_radius="8px",
        border=f"1px solid {rx.color('gray', 6)}",
        margin_bottom="2rem",
    )


def standard_table_actions(
    item_id: str,
    is_active: bool,
    edit_handler: Callable,
    activate_handler: Callable,
    deactivate_handler: Callable,
    can_edit: bool = True,
    can_activate: bool = True,
    additional_actions: Optional[List[rx.Component]] = None
) -> rx.Component:
    """
    Standard table action buttons for management pages.
    
    Args:
        item_id: ID of the item
        is_active: Whether the item is active
        edit_handler: Function to handle edit action
        activate_handler: Function to handle activate action
        deactivate_handler: Function to handle deactivate action
        can_edit: Whether edit is allowed
        can_activate: Whether activate/deactivate is allowed
        additional_actions: Additional action components
    """
    
    actions = []
    
    # Edit button
    if can_edit:
        actions.append(
            rx.button(
                "Edit",
                size="1",
                color_scheme="blue",
                variant="surface",
                on_click=lambda: edit_handler(item_id),
            )
        )
    
    # Activate/Deactivate button
    if can_activate:
        actions.append(
            rx.cond(
                is_active,
                rx.button(
                    "Deactivate",
                    size="1",
                    color_scheme="red",
                    variant="surface",
                    on_click=lambda: deactivate_handler(item_id),
                ),
                rx.button(
                    "Activate",
                    size="1",
                    color_scheme="green",
                    variant="surface",
                    on_click=lambda: activate_handler(item_id),
                ),
            )
        )
    
    # Add additional actions if provided
    if additional_actions:
        actions.extend(additional_actions)
    
    return rx.hstack(
        *actions,
        spacing="2",
    ) 