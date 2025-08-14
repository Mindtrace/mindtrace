import reflex as rx

from poseidon.components import (
    base_management_page,
    standard_filter_bar,
    standard_table_actions,
)
from poseidon.components.popups import add_project_popup, edit_project_popup
from poseidon.components_v2.core.button import button
from poseidon.state.project_management import ProjectData, ProjectManagementState


def project_management_table():
    """Project management table with filtering and actions."""

    def create_project_header(title: str):
        return rx.table.column_header_cell(title)

    def create_project_row(project: ProjectData):
        return rx.table.row(
            rx.table.cell(project.name, cursor="pointer"),
            rx.table.cell(project.description, cursor="pointer"),
            rx.table.cell(project.organization_name, cursor="pointer"),
            rx.table.cell(
                rx.text(
                    rx.cond(project.is_active, "Active", "Inactive"),
                    color=rx.cond(project.is_active, "green", "red"),
                    weight="bold",
                    font_size="12px",
                )
            ),
            rx.table.cell(
                standard_table_actions(
                    item_id=project.id,
                    is_active=project.is_active,
                    edit_handler=lambda id: ProjectManagementState.set_edit_project_data(project),
                    activate_handler=ProjectManagementState.activate_project,
                    deactivate_handler=ProjectManagementState.deactivate_project,
                )
            ),
            _hover={"bg": rx.color(color="gray", shade=4)},
            align="center",
            white_space="nowrap",
        )

    # Dynamic columns based on user role
    project_columns = ["Name", "Description", "Organization", "Status", "Actions"]

    return rx.vstack(
        # Table controls
        rx.hstack(
            rx.hstack(
                rx.text("Rows per page", weight="bold", font_size="12px"),
                rx.select(
                    ["10", "15", "20", "30", "50"],
                    default_value="10",
                    width="80px",
                ),
                align="center",
            ),
            align="center",
            spacing="4",
            width="100%",
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(rx.foreach(project_columns, create_project_header)),
            ),
            rx.table.body(rx.foreach(ProjectManagementState.filtered_projects, create_project_row)),
            width="100%",
            variant="surface",
            max_width="1200px",
            size="1",
        ),
        width="100%",
        align="center",
    )


def project_filter_bar():
    """Filter bar for project management."""
    return standard_filter_bar(
        state_class=ProjectManagementState,
        show_organization_filter=True,
    )


def project_management_content():
    """Main content for project management page."""
    return rx.vstack(
        # Project management table
        project_management_table(),
        # Dialogs
        rx.dialog.root(
            add_project_popup(),
            open=ProjectManagementState.add_project_dialog_open,
            on_open_change=ProjectManagementState.set_add_project_dialog_open,
        ),
        edit_project_popup(),
        width="100%",
        spacing="4",
    )


def project_management_page() -> rx.Component:
    """
    Project management page with role-based access control.
    Uses unified base management page structure.
    """
    return base_management_page(
        title="Project Management",
        description="Manage projects and their assignments",
        state_class=ProjectManagementState,
        content_component=project_management_content,
        actions=[
            button(
                text="Refresh",
                icon=rx.icon("refresh-ccw"),
                variant="secondary",
                size="sm",
                on_click=ProjectManagementState.load_projects,
                loading=ProjectManagementState.loading,
            ),
            button(
                text="Add Project",
                icon=rx.icon("plus"),
                variant="primary",
                size="sm",
                on_click=ProjectManagementState.open_add_project_dialog,
            ),
        ],
        filter_component=project_filter_bar(),
        required_role="admin",
        on_mount=ProjectManagementState.load_projects,
    )
