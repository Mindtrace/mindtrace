"""License Management UI Components

Modern license management components using components_v2 patterns.
Provides dialogs, forms, and tables for license operations.
"""

import reflex as rx
from typing import Dict, Any
from poseidon.state.models import LicenseData

from poseidon.components_v2.core.button import button
from poseidon.components_v2.forms.text_input import text_input
from poseidon.components_v2.forms.select_input import select_input
from poseidon.components_v2.containers.card import card
from poseidon.components_v2.alerts import Alert
from poseidon.backend.database.models.enums import LicenseStatus
from poseidon.state.license_management import LicenseManagementState
from poseidon.styles.global_styles import C, Ty


def license_status_badge(status: str, is_valid: bool = False) -> rx.Component:
    """License status badge with appropriate colors"""
    
    # Use rx.cond instead of Python if statements for Reflex compatibility
    return rx.cond(
        (status == LicenseStatus.ACTIVE) & is_valid,
        rx.badge("Active", color_scheme="green", variant="solid", size="1"),
        rx.cond(
            (status == LicenseStatus.ACTIVE) & ~is_valid,
            rx.badge("Expired", color_scheme="red", variant="solid", size="1"),
            rx.cond(
                status == LicenseStatus.EXPIRED,
                rx.badge("Expired", color_scheme="red", variant="solid", size="1"),
                rx.cond(
                    status == LicenseStatus.CANCELLED,
                    rx.badge("Cancelled", color_scheme="gray", variant="solid", size="1"),
                    rx.badge("Unknown", color_scheme="gray", variant="solid", size="1")
                )
            )
        )
    )


def license_expiry_display(days_until_expiry: int) -> rx.Component:
    """Display license expiry information with color coding"""
    
    # Use rx.cond instead of Python if statements for Reflex compatibility
    return rx.cond(
        days_until_expiry < 0,
        rx.text(
            f"Expired {rx.cond(days_until_expiry < 0, -days_until_expiry, 0)} days ago",
            color="red",
            font_size=Ty.fs_sm,
            weight="medium"
        ),
        rx.cond(
            days_until_expiry == 0,
            rx.text(
                "Expires today",
                color="red",
                font_size=Ty.fs_sm,
                weight="medium"
            ),
            rx.cond(
                days_until_expiry <= 7,
                rx.text(
                    f"Expires in {days_until_expiry} days",
                    color="orange",
                    font_size=Ty.fs_sm,
                    weight="medium"
                ),
                rx.cond(
                    days_until_expiry <= 30,
                    rx.text(
                        f"Expires in {days_until_expiry} days",
                        color="yellow",
                        font_size=Ty.fs_sm,
                        weight="medium"
                    ),
                    rx.text(
                        f"Expires in {days_until_expiry} days",
                        color=C.fg_muted,
                        font_size=Ty.fs_sm
                    )
                )
            )
        )
    )


def add_license_dialog() -> rx.Component:
    """Dialog for adding a new license"""
    
    # Project options for select will come from state
    # LicenseManagementState.available_projects is already in the right format
    
    return rx.dialog.root(
        rx.dialog.trigger(rx.fragment()),
        rx.dialog.content(
            rx.dialog.title("Issue New License"),
            rx.dialog.description(
                "Issue a new license for a project. The license will grant full access to all project features."
            ),
            rx.vstack(
                # Project selection
                select_input(
                    label="Project",
                    placeholder="Select a project",
                    name="project",
                    value=LicenseManagementState.add_license_project_id,
                    on_change=LicenseManagementState.set_add_license_project_id,
                    items=LicenseManagementState.available_projects,
                    required=True,
                    hint="Choose the project to license"
                ),
                
                # Expiration date
                text_input(
                    label="Expiration Date",
                    placeholder="YYYY-MM-DD",
                    name="expires_at",
                    input_type="date",
                    value=LicenseManagementState.add_license_expires_at,
                    on_change=LicenseManagementState.set_add_license_expires_at,
                    required=True,
                    hint="License expiration date"
                ),
                
                # Notes (optional)
                text_input(
                    label="Notes (Optional)",
                    placeholder="Additional notes about this license...",
                    name="notes",
                    value=LicenseManagementState.add_license_notes,
                    on_change=LicenseManagementState.set_add_license_notes,
                    hint="Optional notes for internal tracking"
                ),
                
                spacing="4",
                width="100%"
            ),
            
            # Dialog actions
            rx.flex(
                rx.dialog.close(
                    button(
                        text="Cancel",
                        variant="ghost",
                        on_click=LicenseManagementState.close_add_license_dialog
                    )
                ),
                button(
                    text="Issue License",
                    variant="primary",
                    loading=LicenseManagementState.loading,
                    on_click=LicenseManagementState.add_license
                ),
                spacing="3",
                justify="end",
                margin_top="4"
            ),
            
            style={"max_width": "32rem"},
        ),
        open=LicenseManagementState.add_license_dialog_open,
        on_open_change=LicenseManagementState.set_add_license_dialog_open
    )


def renew_license_dialog() -> rx.Component:
    """Dialog for renewing an existing license"""
    
    return rx.dialog.root(
        rx.dialog.trigger(rx.fragment()),
        rx.dialog.content(
            rx.dialog.title("Renew License"),
            rx.dialog.description(
                f"Renew license {LicenseManagementState.renew_license_key} for {LicenseManagementState.renew_license_project_name}"
            ),
            rx.vstack(
                # Current license info
                card([
                    rx.text("Current License", weight="bold", font_size=Ty.fs_sm),
                    rx.text(f"Key: {LicenseManagementState.renew_license_key}", font_size=Ty.fs_sm),
                    rx.text(f"Project: {LicenseManagementState.renew_license_project_name}", font_size=Ty.fs_sm),
                ]),
                
                # New expiration date
                text_input(
                    label="New Expiration Date",
                    placeholder="YYYY-MM-DD",
                    name="new_expires_at",
                    input_type="date",
                    value=LicenseManagementState.renew_license_new_expires_at,
                    on_change=LicenseManagementState.set_renew_license_new_expires_at,
                    required=True,
                    hint="New license expiration date"
                ),
                
                spacing="4",
                width="100%"
            ),
            
            # Dialog actions
            rx.flex(
                rx.dialog.close(
                    button(
                        text="Cancel",
                        variant="ghost",
                        on_click=LicenseManagementState.close_renew_license_dialog
                    )
                ),
                button(
                    text="Renew License",
                    variant="primary",
                    loading=LicenseManagementState.loading,
                    on_click=LicenseManagementState.renew_license
                ),
                spacing="3",
                justify="end",
                margin_top="4"
            ),
            
            style={"max_width": "32rem"},
        ),
        open=LicenseManagementState.renew_license_dialog_open,
        on_open_change=LicenseManagementState.set_renew_license_dialog_open
    )


def license_details_dialog() -> rx.Component:
    """Dialog for viewing license details"""
    
    license = LicenseManagementState.selected_license
    
    return rx.dialog.root(
        rx.dialog.trigger(rx.fragment()),
        rx.dialog.content(
            rx.dialog.title("License Details"),
            rx.dialog.description("View complete license information"),
            
            rx.vstack(
                # License key and status
                card([
                    rx.hstack(
                        rx.vstack(
                            rx.text("License Key", weight="bold", font_size=Ty.fs_sm),
                            rx.text(license.license_key, font_family="mono", font_size=Ty.fs_sm),
                            align="start",
                            spacing="1"
                        ),
                        rx.vstack(
                            rx.text("Status", weight="bold", font_size=Ty.fs_sm),
                            license_status_badge(
                                license.status,
                                license.is_valid
                            ),
                            align="start",
                            spacing="1"
                        ),
                        justify="between",
                        width="100%"
                    )
                ]),
                
                # Project information
                card([
                    rx.text("Project Information", weight="bold", font_size=Ty.fs_base, margin_bottom="2"),
                    rx.vstack(
                        rx.hstack(
                            rx.text("Project:", weight="medium", font_size=Ty.fs_sm),
                            rx.text(license.project_name, font_size=Ty.fs_sm),
                            justify="between",
                            width="100%"
                        ),
                        rx.cond(
                            LicenseManagementState.is_super_admin_view,
                            rx.hstack(
                                rx.text("Organization:", weight="medium", font_size=Ty.fs_sm),
                                rx.text(license.organization_name, font_size=Ty.fs_sm),
                                justify="between",
                                width="100%"
                            ),
                            rx.fragment()
                        ),
                        spacing="2",
                        width="100%"
                    )
                ]),
                
                # Dates and expiry
                card([
                    rx.text("License Dates", weight="bold", font_size=Ty.fs_base, margin_bottom="2"),
                    rx.vstack(
                        rx.hstack(
                            rx.text("Issued:", weight="medium", font_size=Ty.fs_sm),
                            rx.text(
                                license.issued_at,
                                font_size=Ty.fs_sm
                            ),
                            justify="between",
                            width="100%"
                        ),
                        rx.hstack(
                            rx.text("Expires:", weight="medium", font_size=Ty.fs_sm),
                            rx.text(
                                license.expires_at,
                                font_size=Ty.fs_sm
                            ),
                            justify="between",
                            width="100%"
                        ),
                        rx.hstack(
                            rx.text("Time remaining:", weight="medium", font_size=Ty.fs_sm),
                            license_expiry_display(license.days_until_expiry),
                            justify="between",
                            width="100%"
                        ),
                        spacing="2",
                        width="100%"
                    )
                ]),
                
                # Notes (if any)
                rx.cond(
                    license.notes,
                    card([
                        rx.text("Notes", weight="bold", font_size=Ty.fs_base, margin_bottom="2"),
                        rx.text(license.notes, font_size=Ty.fs_sm)
                    ]),
                    rx.fragment()
                ),
                
                spacing="4",
                width="100%"
            ),
            
            # Dialog actions
            rx.flex(
                rx.dialog.close(
                    button(
                        text="Close",
                        variant="ghost",
                        on_click=LicenseManagementState.close_license_details_dialog
                    )
                ),
                spacing="3",
                justify="end",
                margin_top="4"
            ),
            
            style={"max_width": "40rem"},
        ),
        open=LicenseManagementState.license_details_dialog_open,
        on_open_change=LicenseManagementState.set_license_details_dialog_open
    )


def license_stats_cards() -> rx.Component:
    """Statistics cards for license overview"""
    
    stats = LicenseManagementState.license_stats
    
    return rx.grid(
        # Total licenses
        card([
            rx.vstack(
                rx.text("Total Licenses", font_size=Ty.fs_sm, color=C.fg_muted),
                rx.text(
                    stats.get("total_licenses", 0),
                    font_size="2rem",
                    weight="bold",
                    color=C.fg
                ),
                align="center",
                spacing="1"
            )
        ]),
        
        # Active licenses
        card([
            rx.vstack(
                rx.text("Active Licenses", font_size=Ty.fs_sm, color=C.fg_muted),
                rx.text(
                    stats.get("active_licenses", 0),
                    font_size="2rem",
                    weight="bold",
                    color="green"
                ),
                align="center",
                spacing="1"
            )
        ]),
        
        # Expired licenses
        card([
            rx.vstack(
                rx.text("Expired Licenses", font_size=Ty.fs_sm, color=C.fg_muted),
                rx.text(
                    stats.get("expired_licenses", 0),
                    font_size="2rem",
                    weight="bold",
                    color="red"
                ),
                align="center",
                spacing="1"
            )
        ]),
        
        # Expiring soon
        card([
            rx.vstack(
                rx.text("Expiring Soon", font_size=Ty.fs_sm, color=C.fg_muted),
                rx.text(
                    stats.get("expiring_soon", 0),
                    font_size="2rem",
                    weight="bold",
                    color="orange"
                ),
                align="center",
                spacing="1"
            )
        ]),
        
        columns="4",
        spacing="4",
        width="100%"
    )


def license_table() -> rx.Component:
    """License management table"""
    
    def create_license_header(title: str):
        return rx.table.column_header_cell(
            title,
            style={"font_weight": "600", "color": C.fg}
        )

    def create_license_row(license: LicenseData):
        return rx.table.row(
            # License key
            rx.table.cell(
                rx.text(
                    license.license_key[:12] + "...",
                    font_family="mono",
                    font_size=Ty.fs_sm
                ),
                cursor="pointer",
                on_click=lambda: LicenseManagementState.open_license_details_dialog(license.id)
            ),
            
            # Project name
            rx.table.cell(
                rx.text(license.project_name, font_size=Ty.fs_sm),
                cursor="pointer"
            ),
            
            # Organization (super admin view only)
            rx.cond(
                LicenseManagementState.is_super_admin_view,
                rx.table.cell(
                    rx.text(license.organization_name, font_size=Ty.fs_sm)
                ),
                rx.fragment()
            ),
            
            # Status
            rx.table.cell(
                license_status_badge(license.status, license.is_valid)
            ),
            
            # Expiry
            rx.table.cell(
                license_expiry_display(license.days_until_expiry)
            ),
            
            # Actions
            rx.table.cell(
                rx.hstack(
                    button(
                        text="View",
                        variant="ghost",
                        size="sm",
                        on_click=lambda: LicenseManagementState.open_license_details_dialog(license.id)
                    ),
                    rx.cond(
                        LicenseManagementState.can_manage_licenses(),
                        rx.hstack(
                            button(
                                text="Renew",
                                variant="secondary",
                                size="sm",
                                on_click=lambda: LicenseManagementState.open_renew_license_dialog(license.id)
                            ),
                            rx.cond(
                                license.status == LicenseStatus.ACTIVE,
                                rx.alert_dialog.root(
                                    rx.alert_dialog.trigger(
                                        button(
                                            text="Cancel",
                                            variant="danger",
                                            size="sm"
                                        )
                                    ),
                                    rx.alert_dialog.content(
                                        rx.alert_dialog.title("Cancel License"),
                                        rx.alert_dialog.description(
                                            f"Are you sure you want to cancel license {license.license_key}? This action cannot be undone."
                                        ),
                                        rx.flex(
                                            rx.alert_dialog.cancel(
                                                button("Cancel", variant="ghost")
                                            ),
                                            rx.alert_dialog.action(
                                                button(
                                                    "Yes, Cancel License",
                                                    variant="danger",
                                                    on_click=[
                                                        LicenseManagementState.cancel_license_action(license.id),
                                                        LicenseManagementState.cancel_license
                                                    ]
                                                )
                                            ),
                                            spacing="3",
                                            justify="end",
                                            margin_top="4"
                                        ),
                                    ),
                                ),
                                rx.fragment()
                            ),
                            spacing="2"
                        ),
                        rx.fragment()
                    ),
                    spacing="2"
                )
            ),
            
            _hover={"bg": rx.color(color="gray", shade=2)},
            align="center"
        )

    # Table columns - need to handle dynamically based on super admin view
    # We'll use conditional rendering in the header instead

    return rx.vstack(
        # Table controls
        rx.hstack(
            rx.text(
                "Showing ",
                LicenseManagementState.paginated_licenses.length(),
                " of ",
                LicenseManagementState.total_licenses_count,
                " licenses",
                font_size=Ty.fs_sm,
                color=C.fg_muted
            ),
            justify="between",
            width="100%"
        ),
        
        # Table
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    create_license_header("License Key"),
                    create_license_header("Project"),
                    rx.cond(
                        LicenseManagementState.is_super_admin_view,
                        create_license_header("Organization"),
                        rx.fragment()
                    ),
                    create_license_header("Status"),
                    create_license_header("Expiry"),
                    create_license_header("Actions")
                )
            ),
            rx.table.body(
                rx.foreach(LicenseManagementState.paginated_licenses, create_license_row)
            ),
            width="100%",
            variant="surface"
        ),
        
        # Pagination (if needed)
        rx.cond(
            LicenseManagementState.total_pages > 1,
            rx.hstack(
                button(
                    text="Previous",
                    variant="ghost",
                    size="sm",
                    disabled=LicenseManagementState.current_page <= 1,
                    on_click=LicenseManagementState.previous_page
                ),
                rx.text(
                    f"Page {LicenseManagementState.current_page} of {LicenseManagementState.total_pages}",
                    font_size=Ty.fs_sm
                ),
                button(
                    text="Next",
                    variant="ghost",
                    size="sm",
                    disabled=LicenseManagementState.current_page >= LicenseManagementState.total_pages,
                    on_click=LicenseManagementState.next_page
                ),
                justify="center",
                margin_top="4"
            ),
            rx.fragment()
        ),
        
        spacing="4",
        width="100%"
    )


def license_filter_bar() -> rx.Component:
    """Filter bar for license management"""
    
    status_options = [
        {"id": "all", "name": "All Statuses"},
        {"id": LicenseStatus.ACTIVE, "name": "Active"},
        {"id": LicenseStatus.EXPIRED, "name": "Expired"},
        {"id": LicenseStatus.CANCELLED, "name": "Cancelled"}
    ]
    
    return rx.box(
        rx.hstack(
            # Search input
            text_input(
                placeholder="Search licenses...",
                value=LicenseManagementState.search_query,
                on_change=LicenseManagementState.set_search_query,
                size="medium"
            ),
            
            # Status filter
            select_input(
                placeholder="Filter by status",
                value=LicenseManagementState.license_status_filter,
                on_change=LicenseManagementState.set_license_status_filter,
                items=status_options,
                size="medium"
            ),
            
            # Organization filter (super admin only)
            rx.cond(
                LicenseManagementState.is_super_admin_view,
                select_input(
                    placeholder="Filter by organization",
                    value=LicenseManagementState.organization_filter,
                    on_change=LicenseManagementState.set_organization_filter,
                    items=LicenseManagementState.organization_filter_items,
                    size="medium"
                ),
                rx.fragment()
            ),
            
            # Clear filters button
            button(
                text="Clear Filters",
                variant="ghost",
                size="sm",
                on_click=LicenseManagementState.clear_filters
            ),
            
            spacing="4",
            align="center",
            width="100%"
        ),
        padding="1rem",
        background=rx.color("gray", 2),
        border_radius="8px",
        border=f"1px solid {rx.color('gray', 6)}",
        margin_bottom="2rem"
    )