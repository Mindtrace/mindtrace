"""Poseidon UI Components.

Buridan UI components adapted for Poseidon use cases.
"""

# Core navigation components
from .sidebar import sidebar

# Card components
from .cards import (
    admin_feature_card,
    profile_info_card,
    navigation_action_card,
    user_management_card,
    dashboard_card,
    card_v1,  # Original demo
)

# Form components
from .forms import (
    login_form,
    registration_form,
    contact_form,
    form_input_with_label,
    forms_v1,  # Original demo
)

# Table components
from .tables import (
    user_management_table,
    organization_management_table,
    project_assignments_table,
    tables_v1,  # Original demo
)

# Input components
from .inputs import (
    text_input_with_label,
    email_input,
    password_input,
    search_input,
    textarea_with_label,
    role_filter_select,
    status_filter_select,
    filter_bar,
    success_message,
    error_message,
    warning_message,
    info_message,
    input_v1,  # Original demo
)

# Stats components
from .stats import (
    admin_dashboard_stats,
    user_profile_stats,
    system_overview_stats,
    custom_stats_grid,
    stat_v1,  # Original demo
)

# Button components
from .buttons import (
    primary_action_button,
    secondary_action_button,
    refresh_button,
    danger_action_button,
    success_action_button,
    icon_button,
    link_button,
    action_button_group,
    button_v1,  # Original demo
)

# Page header components
from .headers import (
    app_header,
    page_header,
    page_header_with_actions,
    section_header,
    dashboard_header,
    breadcrumb_header,
    header_v1,
)

# Popup components
from .popups import (
    user_details_popup,
    add_user_popup,
    add_organization_popup,
    edit_user_popup,
    edit_organization_popup,
    notification_popup,
    custom_dialog,
    popups_v1,  # Original demo
)

# Layout components
from .layouts import (
    page_container,
    authenticated_page_wrapper,
    redirect_component,
    content_section,
    two_column_layout,
    three_column_grid,
    card_grid,
    centered_form_layout,
    dashboard_layout,
    loading_wrapper,
    error_boundary,
)

# Utility components
from .utilities import (
    loading_spinner,
    loading_state,
    empty_state,
    status_badge,
    role_badge,
    conditional_wrapper,
    tooltip_wrapper,
    divider,
    skeleton_loader,
    skeleton_card,
    progress_bar,
    avatar,
    access_denied_component,
    authentication_required_component,
)

__all__ = [
    # Navigation
    "app_header",
    "sidebar",
    
    # Cards
    "admin_feature_card",
    "profile_info_card",
    "navigation_action_card",
    "user_management_card",
    "dashboard_card",
    "card_v1",
    
    # Forms
    "login_form",
    "registration_form",
    "contact_form",
    "form_input_with_label",
    "forms_v1",
    
    # Tables
    "user_management_table",
    "organization_management_table",
    "project_assignments_table",
    "tables_v1",
    
    # Inputs
    "text_input_with_label",
    "email_input",
    "password_input",
    "search_input",
    "textarea_with_label",
    "role_filter_select",
    "status_filter_select",
    "filter_bar",
    "success_message",
    "error_message",
    "warning_message",
    "info_message",
    "input_v1",
    
    # Stats
    "admin_dashboard_stats",
    "user_profile_stats",
    "system_overview_stats",
    "custom_stats_grid",
    "stat_v1",
    
    # Buttons
    "primary_action_button",
    "secondary_action_button",
    "refresh_button",
    "danger_action_button",
    "success_action_button",
    "icon_button",
    "link_button",
    "action_button_group",
    "button_v1",
    
    # Page Headers
    "page_header",
    "page_header_with_actions",
    "section_header",
    "dashboard_header",
    "breadcrumb_header",
    "header_v1",
    
    # Popups
    "user_details_popup",
    "add_user_popup",
    "add_organization_popup",
    "edit_user_popup",
    "edit_organization_popup",
    "notification_popup",
    "custom_dialog",
    "popups_v1",
    
    # Layouts
    "page_container",
    "authenticated_page_wrapper",
    "redirect_component",
    "content_section",
    "two_column_layout",
    "three_column_grid",
    "card_grid",
    "centered_form_layout",
    "dashboard_layout",
    "loading_wrapper",
    "error_boundary",
    
    # Utilities
    "loading_spinner",
    "loading_state",
    "empty_state",
    "status_badge",
    "role_badge",
    "conditional_wrapper",
    "tooltip_wrapper",
    "divider",
    "skeleton_loader",
    "skeleton_card",
    "progress_bar",
    "avatar",
    "access_denied_component",
    "authentication_required_component",
] 