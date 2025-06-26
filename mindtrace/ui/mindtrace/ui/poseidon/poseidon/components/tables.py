"""Poseidon Table Components - Buridan UI Styling.

Renamed Buridan UI pantry tables for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx
from poseidon.state.user_management import UserManagementState
from poseidon.state.auth import AuthState
from poseidon.components.popups import edit_user_popup, edit_organization_popup, show_admin_key_popup
from poseidon.state.organization_management import OrganizationManagementState


def user_management_table():
    """User management table - keeps Buridan UI styling."""
    
    def create_user_header(title: str):
        return rx.table.column_header_cell(title)
    
    def create_user_row(user):
        return rx.table.row(
            rx.table.cell(user["username"], cursor="pointer"),
            rx.table.cell(user["email"], cursor="pointer"),
            rx.cond(
                AuthState.is_super_admin,
                rx.table.cell(
                    rx.text(
                        user.get("organization_id", "N/A"),
                        font_size="12px",
                        color=rx.color("gray", 11),
                    )
                ),
                rx.fragment()
            ),
            rx.table.cell(
                rx.text(
                    rx.cond(user["is_active"], "Active", "Inactive"),
                    color=rx.cond(user["is_active"], "green", "red"),
                    weight="bold",
                    font_size="12px",
                )
            ),
            rx.table.cell(
                rx.cond(
                    user["id"] != AuthState.user_id,
                    rx.hstack(
                        rx.cond(
                            UserManagementState.can_edit_user(user["id"]),
                            edit_user_popup(user),
                            None,
                        ),
                        rx.cond(
                            UserManagementState.can_deactivate_user(user["id"]),
                            rx.cond(
                                user["is_active"],
                                rx.button(
                                    "Deactivate", 
                                    size="1",
                                    color_scheme="red",
                                    variant="surface",
                                    cursor="pointer",
                                    on_click=UserManagementState.deactivate_user(user["id"]),
                                ),
                                rx.button(
                                    "Activate",
                                    size="1", 
                                    color_scheme="green",
                                    variant="surface",
                                    cursor="pointer",
                                    on_click=UserManagementState.activate_user(user["id"]),
                                ),
                            ),
                            None,
                        ),
                        spacing="2",
                    ),
                    rx.text(
                        "You",
                        font_size="12px",
                        color=rx.color("gray", 11),
                        style={"font-style": "italic"}
                    ),
                ),
            ),
            _hover={"bg": rx.color(color="gray", shade=4)},
            align="center",
            white_space="nowrap",
        )
    
    # Dynamic columns based on user role
    user_columns = rx.cond(
        AuthState.is_super_admin,
        ["Username", "Email", "Organization", "Status", "Actions"],
        ["Username", "Email", "Status", "Actions"]
    )
    
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
                rx.table.row(rx.foreach(user_columns, create_user_header)),
            ),
            rx.table.body(rx.foreach(UserManagementState.filtered_users, create_user_row)),
            width="100%",
            variant="surface",
            max_width="800px",
            size="1",
        ),
        width="100%",
        align="center",
    )


def data_table(data: list, columns: list, title: str = "Data Table"):
    """Generic data table - keeps Buridan UI styling."""
    
    def create_header(col: str):
        return rx.table.column_header_cell(col)
    
    def create_row(item):
        def fill_cell(value):
            return rx.table.cell(f"{value[1]}", cursor="pointer")
        
        return rx.table.row(
            rx.foreach(item, fill_cell),
            _hover={"bg": rx.color(color="gray", shade=4)},
            align="center",
            white_space="nowrap",
        )
    
    return rx.vstack(
        rx.heading(title, size="3", weight="bold", margin_bottom="4"),
        rx.table.root(
            rx.table.header(
                rx.table.row(rx.foreach(columns, create_header)),
            ),
            rx.table.body(rx.foreach(data, create_row)),
            width="100%",
            variant="surface",
            max_width="800px",
            size="1",
        ),
        width="100%",
        align="center",
    )


def project_assignments_table(assignments: list):
    """Project assignments table - keeps Buridan UI styling."""
    
    def create_assignment_row(assignment):
        return rx.table.row(
            rx.table.cell(assignment.get("project_id", ""), cursor="pointer"),
            rx.table.cell(
                rx.hstack(
                    *[
                        rx.text(
                            role,
                            background=rx.color("blue", 3),
                            color=rx.color("blue", 11),
                            padding="2px 6px",
                            border_radius="4px",
                            font_size="11px",
                            margin="1px",
                        ) for role in assignment.get("roles", [])
                    ],
                    spacing="1",
                    flex_wrap="wrap",
                )
            ),
            rx.table.cell(
                rx.button(
                    "Edit Roles",
                    size="1",
                    color_scheme="gray", 
                    variant="surface",
                    cursor="pointer",
                ),
            ),
            _hover={"bg": rx.color(color="gray", shade=4)},
            align="center",
        )
    
    assignment_columns = ["Project ID", "Roles", "Actions"]
    
    return rx.vstack(
        rx.table.root(
            rx.table.header(
                rx.table.row(rx.foreach(assignment_columns, lambda col: rx.table.column_header_cell(col))),
            ),
            rx.table.body(rx.foreach(assignments, create_assignment_row)),
            width="100%",
            variant="surface",
            max_width="600px",
            size="1",
        ),
        width="100%",
        align="center",
    )


# Keep original demo table for reference
def tables_v1():
    """Original Buridan UI demo table - for reference."""
    demo_data = [
        {"userId": 1, "id": 1, "title": "delectus aut autem", "completed": False},
        {"userId": 1, "id": 2, "title": "quis ut nam facilis", "completed": False},
        {"userId": 1, "id": 3, "title": "fugiat veniam minus", "completed": False},
        {"userId": 1, "id": 4, "title": "et porro tempora", "completed": True},
    ]
    
    class Table(rx.State):
        main_data: list[dict[str, str]] = demo_data
        paginated_data: list[dict[str, str]] = demo_data
        column_names: list[str] = list(demo_data[0].keys())
        limits: list[str] = ["10", "15", "20", "30", "50"]
        current_limit: int = 10
        offset: int = 0
        current_page: int = 1
        number_of_rows: int = len(demo_data)
        total_pages: int = 1

    def create_table_header(title: str):
        return rx.table.column_header_cell(title)

    def create_query_rows(data: dict[str, str]):
        def fill_rows_with_data(data_):
            return rx.table.cell(f"{data_[1]}", cursor="pointer")

        return rx.table.row(
            rx.foreach(data, fill_rows_with_data),
            _hover={"bg": rx.color(color="gray", shade=4)},
            align="center",
            white_space="nowrap",
        )

    def create_pagination():
        return rx.hstack(
            rx.hstack(
                rx.text("Rows per page", weight="bold", font_size="12px"),
                rx.select(
                    Table.limits,
                    default_value="10",
                    width="80px",
                ),
                align_items="center",
            ),
            rx.hstack(
                rx.text(
                    f"Page {Table.current_page} of {Table.total_pages}",
                    width="100px",
                    weight="bold",
                    font_size="12px",
                ),
                rx.button(
                    rx.icon(tag="chevron-left", size=25),
                    color_scheme="gray",
                    variant="surface",
                    size="1",
                    width="32px",
                    height="32px",
                ),
                rx.button(
                    rx.icon(tag="chevron-right", size=25),
                    color_scheme="gray", 
                    variant="surface",
                    size="1",
                    width="32px",
                    height="32px",
                ),
                align_items="center",
                spacing="1",
            ),
            align_items="center",
            spacing="4",
            flex_wrap="wrap",
        )

    return rx.vstack(
        create_pagination(),
        rx.table.root(
            rx.table.header(
                rx.table.row(rx.foreach(Table.column_names, create_table_header)),
            ),
            rx.table.body(rx.foreach(Table.paginated_data, create_query_rows)),
            width="100%",
            variant="surface",
            max_width="800px",
            size="1",
        ),
        width="100%",
        align="center",
    )


def organization_management_table():
    """Organization management table - keeps Buridan UI styling."""
    
    def create_org_header(title: str):
        return rx.table.column_header_cell(title)
    
    def create_org_row(org):
        return rx.table.row(
            rx.table.cell(org.name, cursor="pointer"),
            rx.table.cell(
                rx.cond(
                    org.description,
                    org.description,
                    "No description"
                ),
                cursor="pointer"
            ),
            rx.table.cell(
                rx.text(
                    org.subscription_plan.title(),
                    color=rx.color("blue", 11),
                    weight="medium",
                    font_size="12px",
                )
            ),
            rx.table.cell(
                rx.text(
                    rx.cond(
                        org.max_users,
                        f"{org.max_users} users, ",
                        "50 users, "
                    ) + rx.cond(
                        org.max_projects,
                        f"{org.max_projects} projects",
                        "10 projects"
                    ),
                    font_size="12px",
                    color=rx.color("gray", 11),
                )
            ),
            rx.table.cell(
                rx.text(
                    rx.cond(org.is_active, "Active", "Inactive"),
                    color=rx.cond(org.is_active, "green", "red"),
                    weight="bold",
                    font_size="12px",
                )
            ),
            rx.table.cell(
                rx.hstack(
                    # Show Admin Key button (super admin only)
                    show_admin_key_popup(org),
                    rx.cond(
                        OrganizationManagementState.can_edit_organization(org.id),
                        edit_organization_popup(org),
                        None,
                    ),
                    rx.cond(
                        OrganizationManagementState.can_deactivate_organization(org.id),
                        rx.cond(
                            org.is_active,
                            rx.button(
                                "Deactivate", 
                                size="1",
                                color_scheme="red",
                                variant="surface",
                                cursor="pointer",
                                on_click=OrganizationManagementState.deactivate_organization(org.id),
                            ),
                            rx.button(
                                "Activate",
                                size="1", 
                                color_scheme="green",
                                variant="surface",
                                cursor="pointer",
                                on_click=OrganizationManagementState.activate_organization(org.id),
                            ),
                        ),
                        None,
                    ),
                    spacing="2",
                ),
            ),
            _hover={"bg": rx.color(color="gray", shade=4)},
            align="center",
            white_space="nowrap",
        )
    
    org_columns = ["Name", "Description", "Plan", "Limits", "Status", "Actions"]
    
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
                rx.table.row(rx.foreach(org_columns, create_org_header)),
            ),
            rx.table.body(rx.foreach(OrganizationManagementState.filtered_organizations, create_org_row)),
            width="100%",
            variant="surface",
            max_width="1200px",
            size="1",
        ),
        width="100%",
        align="center",
    )
