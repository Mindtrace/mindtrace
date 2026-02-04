"""License Management Page

License management interface for super admins and admins.
Uses modern components_v2 patterns and base management page structure.
"""

import reflex as rx

from poseidon.components import (
    base_management_page,
)
from poseidon.components.license_management import (
    license_stats_cards,
    license_filter_bar,
    license_table,
    add_license_dialog,
    renew_license_dialog,
    license_details_dialog,
)
from poseidon.components_v2.core.button import button
from poseidon.components_v2.alerts import Alert
from poseidon.backend.database.models.enums import OrgRole
from poseidon.state.license_management import LicenseManagementState


def license_management_content() -> rx.Component:
    """Main content for license management page"""
    
    return rx.vstack(
        # Statistics overview
        rx.cond(
            LicenseManagementState.total_licenses_count > 0,
            rx.vstack(
                rx.heading(
                    "License Overview",
                    size="5",
                    margin_bottom="4"
                ),
                license_stats_cards(),
                spacing="4",
                width="100%",
                margin_bottom="8"
            ),
            rx.fragment()
        ),
        
        # Expiring licenses alert (if any)
        rx.cond(
            LicenseManagementState.expiring_licenses_count > 0,
            Alert.create(
                severity="warning",
                title="Licenses Expiring Soon",
                message=LicenseManagementState.expiring_licenses_message,
            ),
            rx.fragment()
        ),
        
        # Filter bar
        license_filter_bar(),
        
        # License table
        rx.cond(
            LicenseManagementState.filtered_licenses,
            license_table(),
            rx.box(
                rx.vstack(
                    rx.text(
                        "📄",
                        font_size="3rem",
                        margin_bottom="1rem"
                    ),
                    rx.text(
                        "No licenses found",
                        font_size="1.25rem",
                        font_weight="600",
                        color=rx.color("gray", 12),
                        margin_bottom="0.5rem"
                    ),
                    rx.text(
                        "No licenses match your current filters. Try adjusting your search criteria or create a new license.",
                        color=rx.color("gray", 11),
                        text_align="center",
                        margin_bottom="1.5rem"
                    ),
                    rx.cond(
                        LicenseManagementState.can_manage_licenses(),
                        button(
                            text="Issue First License",
                            variant="primary",
                            on_click=LicenseManagementState.open_add_license_dialog
                        ),
                        rx.fragment()
                    ),
                    align="center",
                    spacing="1"
                ),
                padding="3rem 2rem",
                text_align="center"
            )
        ),
        
        # Dialogs
        add_license_dialog(),
        renew_license_dialog(),
        license_details_dialog(),
        
        width="100%",
        spacing="6"
    )


def license_management_actions() -> list:
    """Action buttons for license management page"""
    
    actions = [
        button(
            text="Refresh",
            icon="🔄",
            variant="secondary",
            size="sm",
            on_click=LicenseManagementState.load_licenses,
            loading=LicenseManagementState.loading
        )
    ]
    
    # Add "Issue License" button for super admins
    actions.append(
        rx.cond(
            LicenseManagementState.can_manage_licenses(),
            button(
                text="Issue License",
                icon="➕",
                variant="primary",
                size="sm",
                on_click=LicenseManagementState.open_add_license_dialog
            ),
            rx.fragment()
        )
    )
    
    return actions


def license_management_page() -> rx.Component:
    """
    License management page with role-based access control.
    Super admins can manage all licenses, admins can view their organization's licenses.
    """
    
    return base_management_page(
        title="License Management",
        description="Manage project licenses and access control",
        state_class=LicenseManagementState,
        content_component=license_management_content,
        actions=license_management_actions(),
        filter_component=None,  # Filter is included in content
        required_role=OrgRole.ADMIN,  # Both admins and super admins can access
        on_mount=LicenseManagementState.load_page_data
    )