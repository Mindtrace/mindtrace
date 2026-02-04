"""Poseidon Popup Components - Buridan UI Styling.

Renamed Buridan UI pantry popups for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx
from poseidon.state.user_management import UserManagementState
from poseidon.state.organization_management import OrganizationManagementState
from poseidon.state.auth import AuthState
from poseidon.state.project_management import ProjectManagementState
from poseidon.components_v2.core.button import button


border = rx.color_mode_cond(
    f"1px solid {rx.color('indigo', 3)}",
    f"1px solid {rx.color('slate', 7, True)}",
)
background = rx.color_mode_cond(
    rx.color("indigo", 1),
    rx.color("indigo", 3),
)

box_shadow = rx.color_mode_cond("0px 1px 3px rgba(25, 33, 61, 0.1)", "none")


title = rx.hstack(
    rx.text("Prompt Library", size="6", weight="bold"),
    rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
    width="100%",
    align="center",
    justify="between",
)


def delete_user_confirmation_popup(user_id: str, username: str):
    """Delete user confirmation popup - keeps Buridan UI styling."""
    
    title = rx.hstack(
        rx.text("Delete User", size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )
    
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon(tag="trash-2", size=16),
                "Delete",
                variant="surface",
                color_scheme="red",
                cursor="pointer",
                size="sm",
            ),
        ),
        rx.dialog.content(
            title,
            rx.vstack(
                rx.text(
                    f"Are you sure you want to delete user '{username}'?",
                    color=rx.color("slate", 11),
                ),
                rx.text(
                    "This action cannot be undone. The user will lose access to all resources.",
                    color=rx.color("slate", 12),
                    size="sm",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="surface",
                            color_scheme="gray",
                            cursor="pointer",
                        )
                    ),
                    rx.button(
                        "Delete User",
                        variant="solid",
                        color_scheme="red",
                        cursor="pointer",
                        on_click=UserManagementState.delete_user(user_id),
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                align="start",
            ),
            max_width="400px",
        ),
    )


def user_details_popup(user_data: dict):
    """User details popup - keeps Buridan UI styling."""
    
    title = rx.hstack(
        rx.text("User Details", size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )
    
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon(tag="eye", size=16),
                "View",
                variant="surface",
                color_scheme="blue",
                cursor="pointer",
                size="sm",
            ),
        ),
        rx.dialog.content(
            title,
            rx.vstack(
                rx.vstack(
                    rx.text("Username", color=rx.color("slate", 11)),
                    rx.text(user_data.get("username", ""), color=rx.color("slate", 12)),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Email", color=rx.color("slate", 11)),
                    rx.text(user_data.get("email", ""), color=rx.color("slate", 12)),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Role", color=rx.color("slate", 11)),
                    rx.text(user_data.get("role", ""), color=rx.color("slate", 12)),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Organization", color=rx.color("slate", 11)),
                    rx.text(user_data.get("organization", ""), color=rx.color("slate", 12)),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Status", color=rx.color("slate", 11)),
                    rx.text(user_data.get("status", ""), color=rx.color("slate", 12)),
                    spacing="1",
                ),
                height="45vh",
                overflow="scroll",
                mask="linear-gradient(to bottom, hsl(0, 0%, 0%, 1) 90%, hsl(0, 0%, 0%, 0) 100%)",
                padding="12px 0px",
                spacing="4",
                align="start",
            ),
            max_width="400px",
        ),
    )


def add_user_popup():
    """Add user popup - keeps Buridan UI styling."""
    
    title = rx.hstack(
        rx.text("Add New User", size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )
    
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon(tag="plus", size=16),
                "Add User",
                variant="solid",
                color_scheme="blue",
                cursor="pointer",
            ),
        ),
        rx.dialog.content(
            title,
            rx.vstack(
                rx.vstack(
                    rx.text("Username", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter username",
                        name="username",
                        value=UserManagementState.new_user_username,
                        on_change=UserManagementState.set_new_user_username,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Email", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter email",
                        type="email",
                        name="email",
                        value=UserManagementState.new_user_email,
                        on_change=UserManagementState.set_new_user_email,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Role", color=rx.color("slate", 11)),
                    rx.select(
                        UserManagementState.available_org_roles,
                        placeholder="Select role",
                        value=UserManagementState.new_user_role,
                        on_change=UserManagementState.set_new_user_role,
                    ),
                    spacing="1",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="surface",
                            color_scheme="gray",
                            cursor="pointer",
                        )
                    ),
                    rx.button(
                        "Add User",
                        variant="solid",
                        color_scheme="blue",
                        cursor="pointer",
                        on_click=UserManagementState.add_user,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                align="start",
            ),
            max_width="400px",
        ),
    )


def edit_user_popup(user_data: dict):
    """Edit user popup - keeps Buridan UI styling."""
    
    title = rx.hstack(
        rx.text("Edit User", size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )
    
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                "Edit",
                size="1",
                color_scheme="gray",
                variant="surface",
                cursor="pointer",
                on_click=UserManagementState.set_edit_user_data(user_data),
            ),
        ),
        rx.dialog.content(
            title,
            rx.vstack(
                rx.vstack(
                    rx.text("Username", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter username",
                        name="username",
                        value=UserManagementState.edit_user_username,
                        on_change=UserManagementState.set_edit_user_username,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Email", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter email",
                        type="email",
                        name="email",
                        value=UserManagementState.edit_user_email,
                        on_change=UserManagementState.set_edit_user_email,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Organization Roles", color=rx.color("slate", 11)),
                    rx.select(
                        UserManagementState.edit_user_role_options,
                        placeholder="Select role",
                        value=UserManagementState.edit_user_role,
                        on_change=UserManagementState.set_edit_user_role,
                    ),
                    spacing="1",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="surface",
                            color_scheme="gray",
                            cursor="pointer",
                        )
                    ),
                    rx.dialog.close(
                        rx.button(
                            "Save Changes",
                            variant="solid",
                            color_scheme="blue",
                            cursor="pointer",
                            on_click=UserManagementState.update_user,
                        )
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                align="start",
            ),
            max_width="400px",
        ),
    )


def notification_popup(title: str, message: str, type: str = "info"):
    """Notification popup - keeps Buridan UI styling."""
    
    color_scheme = {
        "success": "green",
        "error": "red",
        "warning": "orange",
        "info": "blue"
    }.get(type, "blue")
    
    popup_title = rx.hstack(
        rx.text(title, size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )
    
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                title,
                variant="surface",
                color_scheme=color_scheme,
                cursor="pointer",
            ),
        ),
        rx.dialog.content(
            popup_title,
            rx.vstack(
                rx.text(
                    message,
                    color=rx.color("slate", 12),
                ),
                rx.dialog.close(
                    rx.button(
                        "OK",
                        variant="solid",
                        color_scheme=color_scheme,
                        cursor="pointer",
                        width="100%",
                    )
                ),
                spacing="4",
                align="start",
            ),
            max_width="400px",
        ),
    )


def custom_dialog(
    trigger_text: str,
    dialog_title: str,
    content: list,
    actions: list = None,
    trigger_variant: str = "surface",
    trigger_color: str = "gray"
):
    """Custom dialog - keeps Buridan UI styling."""
    
    title = rx.hstack(
        rx.text(dialog_title, size="6", weight="bold"),
        rx.dialog.close(rx.icon(tag="x", size=20, cursor="pointer")),
        width="100%",
        align="center",
        justify="between",
    )
    
    # Default actions if none provided
    if not actions:
        actions = [
            rx.dialog.close(
                rx.button(
                    "OK",
                    variant="solid",
                    color_scheme="blue",
                    cursor="pointer",
                )
            )
        ]
    
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                trigger_text,
                variant=trigger_variant,
                color_scheme=trigger_color,
                cursor="pointer",
            ),
        ),
        rx.dialog.content(
            title,
            rx.vstack(
                *content,
                rx.hstack(
                    *actions,
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                align="start",
            ),
            max_width="500px",
        ),
    )





def add_organization_popup():
    """Add organization popup dialog using Buridan UI styling."""
    return rx.dialog.root(
        rx.dialog.trigger(
            button(
                icon=rx.icon("plus"),
                text="Add Organization",
                variant="primary",
                cursor="pointer",
                size="sm",
            )
        ),
        rx.dialog.content(
            rx.dialog.title("Add New Organization"),
            rx.dialog.description("Create a new organization in the system"),
            rx.vstack(
                rx.vstack(
                    rx.text("Organization Name", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter organization name",
                        value=OrganizationManagementState.new_org_name,
                        on_change=OrganizationManagementState.set_new_org_name,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Description", color=rx.color("slate", 11)),
                    rx.text_area(
                        placeholder="Enter organization description",
                        value=OrganizationManagementState.new_org_description,
                        on_change=OrganizationManagementState.set_new_org_description,
                        rows="3",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Subscription Plan", color=rx.color("slate", 11)),
                    rx.select(
                        OrganizationManagementState.available_display_plans,
                        placeholder="Select plan",
                        value=OrganizationManagementState.new_org_plan,
                        on_change=OrganizationManagementState.set_new_org_plan,
                    ),
                    spacing="1",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Max Users", color=rx.color("slate", 11)),
                        rx.input(
                            type="number",
                            value=OrganizationManagementState.new_org_max_users,
                            on_change=OrganizationManagementState.set_new_org_max_users,
                            min="1",
                            max="1000",
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    rx.vstack(
                        rx.text("Max Projects", color=rx.color("slate", 11)),
                        rx.input(
                            type="number",
                            value=OrganizationManagementState.new_org_max_projects,
                            on_change=OrganizationManagementState.set_new_org_max_projects,
                            min="1",
                            max="100",
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="surface",
                            color_scheme="gray",
                            cursor="pointer",
                        )
                    ),
                    rx.button(
                        "Add Organization",
                        variant="solid",
                        color_scheme="blue",
                        cursor="pointer",
                        on_click=OrganizationManagementState.add_organization,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                align="start",
            ),
            max_width="500px",
        ),
    )


def edit_organization_popup(org_data: dict):
    """Edit organization popup dialog using Buridan UI styling."""
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                "Edit",
                size="1",
                color_scheme="blue",
                variant="surface",
                cursor="pointer",
                on_click=OrganizationManagementState.set_edit_org_data(org_data),
            )
        ),
        rx.dialog.content(
            rx.dialog.title("Edit Organization"),
            rx.dialog.description("Update organization information and settings"),
            rx.vstack(
                rx.vstack(
                    rx.text("Organization Name", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter organization name",
                        value=OrganizationManagementState.edit_org_name,
                        on_change=OrganizationManagementState.set_edit_org_name,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Description", color=rx.color("slate", 11)),
                    rx.text_area(
                        placeholder="Enter organization description",
                        value=OrganizationManagementState.edit_org_description,
                        on_change=OrganizationManagementState.set_edit_org_description,
                        rows="3",
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Subscription Plan", color=rx.color("slate", 11)),
                    rx.select(
                        OrganizationManagementState.available_display_plans,
                        placeholder="Select plan",
                        value=OrganizationManagementState.edit_org_plan,
                        on_change=OrganizationManagementState.set_edit_org_plan,
                    ),
                    spacing="1",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("Max Users", color=rx.color("slate", 11)),
                        rx.input(
                            type="number",
                            value=OrganizationManagementState.edit_org_max_users,
                            on_change=OrganizationManagementState.set_edit_org_max_users,
                            min="1",
                            max="1000",
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    rx.vstack(
                        rx.text("Max Projects", color=rx.color("slate", 11)),
                        rx.input(
                            type="number",
                            value=OrganizationManagementState.edit_org_max_projects,
                            on_change=OrganizationManagementState.set_edit_org_max_projects,
                            min="1",
                            max="100",
                        ),
                        spacing="1",
                        flex="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="surface",
                            color_scheme="gray",
                            cursor="pointer",
                        )
                    ),
                    rx.dialog.close(
                        rx.button(
                            "Save Changes",
                            variant="solid",
                            color_scheme="blue",
                            cursor="pointer",
                            on_click=OrganizationManagementState.update_organization,
                        )
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                align="start",
            ),
            max_width="500px",
        ),
    )


def show_admin_key_popup(org_data: dict):
    """Popup to show the admin registration key for an organization (super admin only)."""
    return rx.cond(
        AuthState.is_super_admin,
        rx.dialog.root(
            rx.dialog.trigger(
                rx.button(
                    "Show Admin Key",
                    size="1",
                    color_scheme="orange",
                    variant="surface",
                    cursor="pointer",
                )
            ),
            rx.dialog.content(
                rx.dialog.title(f"Admin Registration Key for {org_data['name']}"),
                rx.dialog.description("This key is required for registering new organization admins."),
                rx.vstack(
                    rx.input(
                        value=org_data.get("admin_key", ""),
                        read_only=True,
                        width="100%",
                        id=f"admin-key-input-{org_data['id']}"
                    ),
                    rx.button(
                        "Copy Key",
                        size="1",
                        color_scheme="blue",
                        variant="solid",
                        cursor="pointer",
                        on_click=rx.call_script(f"navigator.clipboard.writeText(document.getElementById('admin-key-input-{org_data['id']}').value)")
                    ),
                    spacing="3",
                    width="100%",
                ),
                max_width="400px",
            ),
        ),
        None,
    )


def add_project_popup():
    """Add project popup form."""
    return rx.dialog.content(
            rx.dialog.title("Add New Project"),
            rx.dialog.description("Create a new project in the system"),
            rx.vstack(
                rx.vstack(
                    rx.text("Project Name", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter project name",
                        value=ProjectManagementState.new_project_name,
                        on_change=ProjectManagementState.set_new_project_name,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Description", color=rx.color("slate", 11)),
                    rx.text_area(
                        placeholder="Enter project description",
                        value=ProjectManagementState.new_project_description,
                        on_change=ProjectManagementState.set_new_project_description,
                        rows="3",
                    ),
                    spacing="1",
                ),
                # Organization selection - only show for super admins
                rx.cond(
                    ProjectManagementState.show_organization_selector,
                    rx.vstack(
                        rx.text("Organization", color=rx.color("slate", 11)),
                        rx.select(
                            ProjectManagementState.organization_options,
                            placeholder="Select organization",
                            value=ProjectManagementState.new_project_organization_name,
                            on_change=ProjectManagementState.set_new_project_organization_by_name,
                        ),
                        spacing="1",
                    ),
                    # For regular admins, show read-only organization name
                    rx.cond(
                        ProjectManagementState.new_project_organization_name != "",
                        rx.vstack(
                            rx.text("Organization", color=rx.color("slate", 11)),
                            rx.input(
                                value=ProjectManagementState.new_project_organization_name,
                                read_only=True,
                                background=rx.color("gray", 2),
                                color=rx.color("slate", 11),
                            ),
                            spacing="1",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            rx.dialog.close(
                rx.hstack(
                    rx.button(
                        "Cancel",
                        color_scheme="gray",
                        variant="surface",
                        on_click=ProjectManagementState.close_add_project_dialog,
                    ),
                    rx.button(
                        "Add Project",
                        color_scheme="blue",
                        on_click=ProjectManagementState.add_project,
                    ),
                    spacing="2",
                    justify="end",
                ),
            ),
            max_width="400px",
        )


def edit_project_popup():
    """Edit project popup form."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Edit Project"),
            rx.dialog.description("Update project information"),
            rx.vstack(
                rx.vstack(
                    rx.text("Project Name", color=rx.color("slate", 11)),
                    rx.input(
                        placeholder="Enter project name",
                        value=ProjectManagementState.edit_project_name,
                        on_change=ProjectManagementState.set_edit_project_name,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Description", color=rx.color("slate", 11)),
                    rx.text_area(
                        placeholder="Enter project description",
                        value=ProjectManagementState.edit_project_description,
                        on_change=ProjectManagementState.set_edit_project_description,
                        rows="3",
                    ),
                    spacing="1",
                ),
                # Organization selection - only show for super admins
                rx.cond(
                    ProjectManagementState.show_organization_selector,
                    rx.vstack(
                        rx.text("Organization", color=rx.color("slate", 11)),
                        rx.select(
                            ProjectManagementState.organization_options,
                            placeholder="Select organization",
                            value=ProjectManagementState.edit_project_organization_name,
                            on_change=ProjectManagementState.set_edit_project_organization_by_name,
                        ),
                        spacing="1",
                    ),
                    # For regular admins, show read-only organization name
                    rx.cond(
                        ProjectManagementState.edit_project_organization_name != "",
                        rx.vstack(
                            rx.text("Organization", color=rx.color("slate", 11)),
                            rx.input(
                                value=ProjectManagementState.edit_project_organization_name,
                                read_only=True,
                                background=rx.color("gray", 2),
                                color=rx.color("slate", 11),
                            ),
                            spacing="1",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            rx.dialog.close(
                rx.hstack(
                    rx.button(
                        "Cancel",
                        color_scheme="gray",
                        variant="surface",
                        on_click=ProjectManagementState.clear_edit_project_form,
                    ),
                    rx.button(
                        "Update Project",
                        color_scheme="blue",
                        on_click=ProjectManagementState.update_project,
                    ),
                    spacing="2",
                    justify="end",
                ),
            ),
            max_width="400px",
        ),
        open=ProjectManagementState.edit_project_id != "",
        on_open_change=ProjectManagementState.handle_edit_dialog_change,
    )


def assign_project_popup():
    """Project assignment popup form."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Assign User to Project"),
            rx.dialog.description(
                rx.text("Assign ", rx.text(UserManagementState.assignment_user_name, weight="bold"), " to a project")
            ),
            rx.vstack(
                rx.vstack(
                    rx.text("Project", color=rx.color("slate", 11)),
                    rx.select(
                        UserManagementState.available_project_options,
                        placeholder="Select project",
                        value=UserManagementState.assignment_project_name,
                        on_change=UserManagementState.set_assignment_project_by_name,
                    ),
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Project Roles", color=rx.color("slate", 11)),
                    rx.text("Select one or more roles for this project:", font_size="12px", color=rx.color("gray", 11)),
                    rx.vstack(
                        rx.foreach(
                            UserManagementState.available_project_roles,
                            lambda role: rx.hstack(
                                rx.checkbox(
                                    checked=UserManagementState.assignment_roles.contains(role),
                                    on_change=lambda checked: UserManagementState.toggle_assignment_role(role),
                                ),
                                rx.text(
                                    role.replace("_", " ").title(),
                                    font_size="14px",
                                ),
                                spacing="2",
                                align="center",
                            )
                        ),
                        spacing="2",
                        align="start",
                    ),
                    spacing="1",
                ),
                spacing="4",
                width="100%",
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.button(
                        "Cancel",
                        color_scheme="gray",
                        variant="surface",
                        on_click=UserManagementState.close_assignment_dialog,
                    )
                ),
                rx.button(
                    "Assign to Project",
                    color_scheme="blue",
                    on_click=UserManagementState.assign_user_to_project_from_dialog,
                    loading=UserManagementState.loading,
                ),
                spacing="2",
                justify="end",
            ),
            max_width="400px",
        ),
        open=UserManagementState.assignment_dialog_open,
        on_open_change=UserManagementState.set_assignment_dialog_open,
        on_mount=UserManagementState.load_projects_for_assignment,
    )


def project_management_popup():
    """Project management popup for viewing and removing user project assignments."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Manage Project Assignments"),
            rx.dialog.description(
                rx.text("Manage project assignments for ", rx.text(UserManagementState.project_management_user_name, weight="bold"))
            ),
            rx.vstack(
                rx.text("Current Project Assignments:", weight="bold", color=rx.color("slate", 11)),
                rx.cond(
                    UserManagementState.project_management_user_assignments,
                    rx.vstack(
                        rx.foreach(
                            UserManagementState.project_management_user_assignments,
                            lambda assignment: rx.hstack(
                                rx.vstack(
                                    rx.text(
                                        assignment.get("project_name", "Unknown Project"),
                                        weight="medium",
                                        color=rx.color("blue", 11),
                                    ),
                                    rx.text(
                                        assignment.get("role_display", "Role: No role"),
                                        color=rx.color("green", 11),
                                        font_size="12px",
                                        weight="medium"
                                    ),
                                    align="start",
                                    spacing="1"
                                ),
                                rx.spacer(),
                                rx.button(
                                    "Remove",
                                    on_click=lambda project_id=assignment.get("project_id"): UserManagementState.remove_user_from_project(
                                        UserManagementState.project_management_user_id, 
                                        project_id
                                    ),
                                    size="2",
                                    color_scheme="red",
                                    variant="soft",
                                ),
                                width="100%",
                                align="center",
                                padding="8px",
                                border=f"1px solid {rx.color('gray', 4)}",
                                border_radius="6px",
                            )
                        ),
                        spacing="2",
                        width="100%"
                    ),
                    rx.text(
                        "No project assignments",
                        color=rx.color("gray", 9),
                        style={"font-style": "italic"}
                    )
                ),
                rx.separator(),
                rx.hstack(
                    rx.button(
                        "Add Project Assignment",
                        on_click=lambda: [
                            UserManagementState.open_assignment_dialog(UserManagementState.project_management_user_id),
                            UserManagementState.close_project_management_dialog()
                        ],
                        size="2",
                        color_scheme="blue",
                    ),
                    rx.spacer(),
                    rx.button(
                        "Close",
                        on_click=UserManagementState.close_project_management_dialog,
                        size="2",
                        color_scheme="gray",
                    ),
                    width="100%",
                    justify="end"
                ),
                spacing="4",
                width="100%"
            ),
            max_width="500px",
            padding="20px"
        ),
        open=UserManagementState.project_management_dialog_open,
        on_open_change=UserManagementState.set_project_management_dialog_open,
    )


def camera_assignment_popup():
    """Camera assignment popup form."""
    from poseidon.state.camera import CameraState
    
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Manage Camera Assignment"),
            rx.dialog.description(
                rx.text("Assign ", rx.text(CameraState.assignment_camera_name, weight="bold"), " to a project")
            ),
            rx.vstack(
                rx.vstack(
                    rx.text("Current Assignment", color=rx.color("slate", 11)),
                                         rx.text(
                         rx.cond(
                             CameraState.assignment_camera_current_project != "Unassigned",
                             rx.text("Currently assigned to: ", rx.text(CameraState.assignment_camera_current_project, weight="bold")),
                             rx.text("Currently unassigned", style={"font-style": "italic"}, color=rx.color("gray", 9))
                         ),
                         font_size="14px",
                         color=rx.color("gray", 11),
                     ),
                    spacing="1",
                ),
                    rx.vstack(
                     rx.text("New Project Assignment", color=rx.color("slate", 11)),
                     rx.select(
                         CameraState.available_project_options,
                         placeholder="Select project",
                         value=CameraState.assignment_project_name,
                         on_change=CameraState.set_assignment_project_by_name,
                     ),
                     rx.cond(
                         CameraState.is_super_admin,
                         rx.text(
                             "Note: As a super admin, you can assign cameras to projects across all organizations",
                             font_size="12px",
                             color=rx.color("blue", 11),
                             style={"font-style": "italic"}
                         ),
                     ),
                     spacing="1",
                 ),
                    rx.cond(
                     CameraState.assignment_camera_current_project != "Unassigned",
                     rx.vstack(
                         rx.text("Quick Actions", color=rx.color("slate", 11)),
                         rx.button(
                             "Unassign from Current Project",
                             color_scheme="red",
                             variant="surface",
                             on_click=lambda: CameraState.unassign_camera_from_project_by_name(CameraState.assignment_camera_name),
                             loading=CameraState.is_loading,
                             width="100%",
                         ),
                         spacing="1",
                     ),
                 ),
                spacing="4",
                width="100%",
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.button(
                        "Cancel",
                        color_scheme="gray",
                        variant="surface",
                        on_click=CameraState.close_camera_assignment_dialog,
                    )
                ),
                rx.button(
                    "Assign to Project",
                    color_scheme="blue",
                    on_click=CameraState.assign_camera_to_project_from_dialog,
                    loading=CameraState.is_loading,
                    disabled=CameraState.assignment_project_id == "",
                ),
                spacing="2",
                justify="end",
            ),
            max_width="400px",
        ),
        open=CameraState.assignment_dialog_open,
        on_open_change=CameraState.set_camera_assignment_dialog_open,
    )
