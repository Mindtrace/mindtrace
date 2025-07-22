"""Poseidon UI Components.

Modern component library with mindtrace styling as the primary choice.
Mindtrace components provide superior animations, styling, and user experience.
"""

# === PRIMARY MINDTRACE COMPONENTS (RECOMMENDED) ===
# These provide superior styling, animations, and user experience

# Mindtrace form components (PRIMARY CHOICE)
from .mindtrace_forms import (
    input_mindtrace,
    input_with_label_mindtrace,
    input_with_hint_mindtrace,
    select_mindtrace,
    button_mindtrace,
    link_mindtrace,
)

# Mindtrace layout components
from .mindtrace_layouts import (
    background_mindtrace,
    page_layout_mindtrace,
    css_animations_mindtrace,
)

# Mindtrace branding components
from .mindtrace_branding import (
    logo_mindtrace,
)

# Mindtrace card components
from .mindtrace_cards import (
    card_mindtrace,
)

# Mindtrace header components
from .mindtrace_headers import (
    header_mindtrace,
)

# === SECONDARY COMPONENTS ===
# Use these for specific functionality not covered by mindtrace components

# Core navigation components
from .sidebar import sidebar

# Card components
from .cards import (
    admin_feature_card,
    profile_info_card,
    navigation_action_card,
    user_management_card,
    dashboard_card,
)

# Form components
from .forms import (
    login_form,
    registration_form,
    contact_form,
    form_input_with_label,
)

# Table components
from .tables import (
    user_management_table,
    organization_management_table,
    project_assignments_table,
)

# Input components
from .inputs import (
    textarea_with_label,
    role_filter_select,
    status_filter_select,
    filter_bar,
    success_message,
    error_message,
    warning_message,
    info_message,
)

# Stats components
from .stats import (
    admin_dashboard_stats,
    user_profile_stats,
    system_overview_stats,
    custom_stats_grid,
)

# Button components
from .buttons import (
    refresh_button,
    icon_button,
    link_button,
    action_button_group,
)

# Page header components
from .headers import (
    app_header,
    page_header,
    page_header_with_actions,
    section_header,
    dashboard_header,
    breadcrumb_header,
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
    assign_project_popup,
    project_management_popup,
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

# Base management components
from .base_management import (
    base_management_page,
    standard_filter_bar,
    standard_table_actions,
)

# Mindtrace components are now imported at the top as primary components

__all__ = [
    # === PRIMARY MINDTRACE COMPONENTS (RECOMMENDED) ===
    # Form components (PRIMARY CHOICE)
    "input_mindtrace",
    "input_with_label_mindtrace", 
    "input_with_hint_mindtrace",
    "select_mindtrace",
    "button_mindtrace",
    "link_mindtrace",
    
    # Layout components
    "background_mindtrace",
    "page_layout_mindtrace",
    "css_animations_mindtrace",
    
    # Branding components
    "logo_mindtrace",
    
    # Card components
    "card_mindtrace",
    
    # Header components
    "header_mindtrace",
    
    # === SECONDARY COMPONENTS ===
    # Navigation
    "app_header",
    "sidebar",
    
    # Cards
    "admin_feature_card",
    "profile_info_card",
    "navigation_action_card",
    "user_management_card",
    "dashboard_card",
    
    # Forms
    "login_form",
    "registration_form",
    "contact_form",
    "form_input_with_label",
    
    # Tables
    "user_management_table",
    "organization_management_table",
    "project_assignments_table",
    
    # Inputs
    "textarea_with_label",
    "role_filter_select",
    "status_filter_select",
    "filter_bar",
    "success_message",
    "error_message",
    "warning_message",
    "info_message",
    
    # Stats
    "admin_dashboard_stats",
    "user_profile_stats",
    "system_overview_stats",
    "custom_stats_grid",
    
    # Buttons
    "refresh_button",
    "icon_button",
    "link_button",
    "action_button_group",
    
    # Page Headers
    "page_header",
    "page_header_with_actions",
    "section_header",
    "dashboard_header",
    "breadcrumb_header",
    
    # Popups
    "user_details_popup",
    "add_user_popup",
    "add_organization_popup",
    "edit_user_popup",
    "edit_organization_popup",
    "notification_popup",
    "custom_dialog",
    "assign_project_popup",
    "project_management_popup",
    
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
    
    # Base Management
    "base_management_page",
    "standard_filter_bar",
    "standard_table_actions",
] 