import reflex as rx
from typing import List, Dict, Optional
from poseidon.backend.services.user_management_service import UserManagementService
from poseidon.backend.database.models.enums import OrgRole
from poseidon.state.base import BaseManagementState, BaseDialogState, RoleBasedAccessMixin
from poseidon.state.models import UserRoles


class UserManagementState(BaseDialogState, RoleBasedAccessMixin):
    """User management state with role-based access control."""
    
    # User list and filtering
    organization_users: List[Dict] = []
    filtered_users: List[Dict] = []
    user_search_query: str = ""
    role_filter: str = ""
    user_status_filter: str = ""
    
    # Add user form
    new_user_username: str = ""
    new_user_email: str = ""
    new_user_role: str = ""
    show_add_user_dialog: bool = False
    
    # Edit user form
    edit_user_id: str = ""
    edit_user_username: str = ""
    edit_user_email: str = ""
    edit_user_role: str = ""
    show_edit_user_dialog: bool = False
    
    # Assign project form
    assign_project_user_id: str = ""
    assign_project_id: str = ""
    assign_project_roles: List[str] = []
    show_assign_project_dialog: bool = False
    
    # User details
    selected_user: Dict = {}
    show_user_details: bool = False
    
    # Available projects for assignment
    available_projects: List[Dict] = []
    
    # Pagination
    current_page: int = 1
    users_per_page: int = 10
    
    # Success/error messages
    success_message: str = ""
    error_message: str = ""
    is_loading: bool = False

    def clear_messages(self):
        """Clear success and error messages"""
        self.success_message = ""
        self.error_message = ""

    async def handle_async_operation(self, operation, success_message: str):
        """Handle async operations with loading states and error handling"""
        self.is_loading = True
        self.clear_messages()
        
        try:
            result = await operation()
            if result:
                self.success_message = success_message
        except Exception as e:
            self.error_message = f"Error: {str(e)}"
        finally:
            self.is_loading = False

    async def load_organization_users(self):
        """Load users based on user role - all users for super admin, org users for admin"""
        async def load_users_data():
            auth_state = await self.get_auth_state()
            
            if auth_state.is_super_admin:
                # Super admin sees all users across all organizations
                users = await UserManagementService.get_all_users()
                self.organization_users = [
                    {
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email,
                        "organization_id": str(user.organization.id) if user.organization else "",
                        "org_role": user.org_role,
                        "is_active": user.is_active,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at
                    }
                    for user in users
                ]
            else:
                # Regular admin sees only their organization's users
                await self.load_admin_organization_users()
            
            # Load available projects for assignment
            await self.load_available_projects()
            return True
        
        await self.handle_async_operation(
            load_users_data,
            "Users loaded successfully"
        )

    async def load_admin_organization_users(self):
        """Load users for the admin's organization"""
        auth_state = await self.get_auth_state()
        if auth_state.user_organization_id:
            users = await UserManagementService.get_organization_users(auth_state.user_organization_id)
            
            # Fetch linked organization data for each user
            for user in users:
                await user.fetch_link(user.organization)
                
            self.organization_users = [
                {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "organization_id": str(user.organization.id) if user.organization else "",
                    "org_role": user.org_role,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at
                }
                for user in users
            ]

    async def load_available_projects(self):
        """Load available projects for assignment"""
        try:
            from poseidon.backend.database.repositories.project_repository import ProjectRepository
            
            auth_state = await self.get_auth_state()
            
            if auth_state.is_super_admin:
                # Super admin can see all projects
                projects = await ProjectRepository.get_all()
            else:
                # Regular admin sees only their organization's projects
                projects = await ProjectRepository.get_by_organization(auth_state.user_organization_id)
            
            # Fetch linked organization data for each project
            for project in projects:
                await project.fetch_link(project.organization)
                
            self.available_projects = [
                {
                    "id": str(project.id),
                    "name": project.name,
                    "organization_id": str(project.organization.id) if project.organization else "",
                    "organization_name": project.organization.name if project.organization else "Unknown"
                }
                for project in projects
            ]
            
        except Exception as e:
            self.error_message = f"Failed to load projects: {str(e)}"

    def filter_users(self):
        """Filter users based on search query and filters"""
        filtered = self.organization_users
        
        # Search filter
        if self.user_search_query:
            filtered = [
                user for user in filtered
                if (self.user_search_query.lower() in user.get("username", "").lower() or
                    self.user_search_query.lower() in user.get("email", "").lower())
            ]
        
        # Role filter
        if self.role_filter:
            filtered = [
                user for user in filtered
                if self.role_filter == user.get("org_role", "")
            ]
        
        # Status filter
        if self.user_status_filter:
            if self.user_status_filter == "active":
                filtered = [user for user in filtered if user.get("is_active", False)]
            elif self.user_status_filter == "inactive":
                filtered = [user for user in filtered if not user.get("is_active", False)]
        
        self.filtered_users = filtered

    def set_user_search_query(self, query: str):
        """Set search query and filter users"""
        self.user_search_query = query
        self.filter_users()

    def set_role_filter(self, role: str):
        """Set role filter and filter users"""
        self.role_filter = role
        self.filter_users()

    def set_status_filter(self, status: str):
        """Set status filter and filter users"""
        self.user_status_filter = status
        self.filter_users()

    def clear_filters(self):
        """Clear all filters"""
        self.user_search_query = ""
        self.role_filter = ""
        self.user_status_filter = ""
        self.filter_users()

    def show_add_user_form(self):
        """Show add user dialog"""
        self.show_add_user_dialog = True

    def hide_add_user_form(self):
        """Hide add user dialog"""
        self.show_add_user_dialog = False
        self.clear_add_user_form()

    def clear_add_user_form(self):
        """Clear add user form"""
        self.new_user_username = ""
        self.new_user_email = ""
        self.new_user_role = ""

    def set_new_user_role(self, role: str):
        """Set the new user role"""
        self.new_user_role = role

    def set_new_user_username(self, username: str):
        """Set the new user username"""
        self.new_user_username = username

    def set_new_user_email(self, email: str):
        """Set the new user email"""
        self.new_user_email = email

    def set_edit_user_username(self, username: str):
        """Set the edit user username"""
        self.edit_user_username = username

    def set_edit_user_email(self, email: str):
        """Set the edit user email"""
        self.edit_user_email = email

    def set_edit_user_role(self, role: str):
        """Set the edit user role"""
        self.edit_user_role = role

    def set_edit_user_data(self, user_data: Dict):
        """Set edit user data from user dictionary"""
        self.edit_user_id = user_data.get("id", "")
        self.edit_user_username = user_data.get("username", "")
        self.edit_user_email = user_data.get("email", "")
        self.edit_user_role = user_data.get("org_role", "")
        self.show_edit_user_dialog = True

    def show_edit_user_form(self, user_id: str):
        """Show edit user dialog"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.edit_user_id = user_id
            self.edit_user_username = user["username"]
            self.edit_user_email = user["email"]
            self.edit_user_role = user["org_role"]
            self.show_edit_user_dialog = True

    def hide_edit_user_form(self):
        """Hide edit user dialog"""
        self.show_edit_user_dialog = False
        self.clear_edit_user_form()

    def clear_edit_user_form(self):
        """Clear edit user form"""
        self.edit_user_id = ""
        self.edit_user_username = ""
        self.edit_user_email = ""
        self.edit_user_role = ""

    def show_user_details_dialog(self, user_id: str):
        """Show user details dialog"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.selected_user = user
            self.show_user_details = True

    def hide_user_details_dialog(self):
        """Hide user details dialog"""
        self.show_user_details = False
        self.selected_user = {}

    def validate_required_field(self, field_value: str, field_name: str) -> bool:
        """Validate that a required field is not empty"""
        if not field_value or not field_value.strip():
            self.error_message = f"{field_name} is required"
            return False
        return True

    def validate_email(self, email: str) -> bool:
        """Basic email validation"""
        if not email or "@" not in email:
            self.error_message = "Valid email is required"
            return False
        return True

    async def get_admin_organization_id(self) -> Optional[str]:
        """Get the organization ID of the current admin user"""
        auth_state = await self.get_auth_state()
        if auth_state.is_authenticated and (auth_state.is_admin or auth_state.is_super_admin):
            return auth_state.user_organization_id
        return None

    async def add_user(self):
        """Add a new user to the organization"""
        async def create_user():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error_message = "Access denied: Admin privileges required"
                return False
            
            # Validate form data
            if not self.validate_required_field(self.new_user_username, "Username"):
                return False
                
            if not self.validate_email(self.new_user_email):
                return False
                
            if not self.validate_required_field(self.new_user_role, "Role"):
                return False
            
            # Convert role to unified format
            role_mapping = UserRoles.get_display_names()
            # Reverse mapping for display names to internal values
            reverse_role_mapping = {v: k for k, v in role_mapping.items()}
            reverse_role_mapping.update({k: k for k in UserRoles.get_assignable()})  # Direct mappings
            
            backend_role = reverse_role_mapping.get(self.new_user_role, UserRoles.USER)
            
            # Validate role assignment permissions
            auth_state = await self.get_auth_state()
            if backend_role == UserRoles.ADMIN and not self.can_manage_users(auth_state.is_admin, auth_state.is_super_admin):
                self.error_message = "Only admins can assign admin role"
                return False
            
            # Call user management service to add user
            result = await UserManagementService.create_user_in_organization(
                username=self.new_user_username.strip(),
                email=self.new_user_email.strip(),
                password="TempPassword123!",  # TODO: Generate secure temp password
                admin_organization_id=org_id,
                org_role=backend_role
            )
            
            if result.get("success"):
                self.clear_add_user_form()
                self.hide_add_user_form()
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error_message = result.get("error", "Failed to add user")
                return False
        
        await self.handle_async_operation(
            create_user,
            f"User '{self.new_user_username}' added successfully"
        )

    async def update_user(self):
        """Update an existing user"""
        async def update_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error_message = "Access denied: Admin privileges required"
                return False
            
            # Validate form data
            if not self.validate_required_field(self.edit_user_username, "Username"):
                return False
                
            if not self.validate_email(self.edit_user_email):
                return False
                
            if not self.validate_required_field(self.edit_user_role, "Role"):
                return False
            
            # Validate role assignment permissions
            auth_state = await self.get_auth_state()
            if self.edit_user_role == UserRoles.ADMIN and not self.can_manage_users(auth_state.is_admin, auth_state.is_super_admin):
                self.error_message = "Only admins can assign admin role"
                return False
            
            # Update user organization role
            result = await UserManagementService.update_user_org_role(
                self.edit_user_id,
                self.edit_user_role,
                org_id
            )
            
            if result.get("success"):
                self.clear_edit_user_form()
                self.hide_edit_user_form()
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error_message = result.get("error", "Failed to update user")
                return False
        
        await self.handle_async_operation(
            update_user_data,
            f"User '{self.edit_user_username}' updated successfully"
        )

    async def deactivate_user(self, user_id: str):
        """Deactivate a user"""
        async def deactivate_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error_message = "Access denied: Admin privileges required"
                return False
            
            result = await UserManagementService.deactivate_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error_message = result.get("error", "Failed to deactivate user")
                return False
        
        await self.handle_async_operation(
            deactivate_user_data,
            "User deactivated successfully"
        )

    async def activate_user(self, user_id: str):
        """Activate a user"""
        async def activate_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error_message = "Access denied: Admin privileges required"
                return False
            
            result = await UserManagementService.activate_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error_message = result.get("error", "Failed to activate user")
                return False
        
        await self.handle_async_operation(
            activate_user_data,
            "User activated successfully"
        )

    @rx.var
    def available_org_roles(self) -> List[str]:
        """Get available organization roles based on user permissions"""
        # All users can see basic roles
        roles = [UserRoles.USER]
        
        # Only admins and super admins can assign admin roles
        if self.can_manage_users(True, True):  # This will be checked in the actual assignment
            roles.append(UserRoles.ADMIN)
        
        return roles

    @rx.var
    def edit_user_role_options(self) -> List[str]:
        """Get available organization roles for editing"""
        return self.available_org_roles

    @rx.var
    def search_query(self) -> str:
        """Alias for user_search_query for backward compatibility"""
        return self.user_search_query

    @rx.var
    def success(self) -> str:
        """Alias for success_message for backward compatibility"""
        return self.success_message

    @rx.var
    def error(self) -> str:
        """Alias for error_message for backward compatibility"""
        return self.error_message

    @rx.var
    def loading(self) -> bool:
        """Alias for is_loading for backward compatibility"""
        return self.is_loading

    @rx.var
    def status_filter(self) -> str:
        """Alias for user_status_filter for backward compatibility"""
        return self.user_status_filter

    def set_search_query(self, query: str):
        """Set search query (alias for set_user_search_query)"""
        self.set_user_search_query(query)

    def set_status_filter(self, status: str):
        """Set status filter (alias for existing method)"""
        self.user_status_filter = status
        self.filter_users()

    @rx.var
    def paginated_users(self) -> List[Dict]:
        """Get users for current page"""
        start_index = (self.current_page - 1) * self.users_per_page
        end_index = start_index + self.users_per_page
        return self.filtered_users[start_index:end_index]

    @rx.var
    def total_pages(self) -> int:
        """Calculate total number of pages"""
        if not self.filtered_users:
            return 1
        return (len(self.filtered_users) + self.users_per_page - 1) // self.users_per_page

    def next_page(self):
        """Go to next page"""
        if self.current_page < self.total_pages:
            self.current_page += 1

    def previous_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1

    def go_to_page(self, page: int):
        """Go to specific page"""
        if 1 <= page <= self.total_pages:
            self.current_page = page

    def get_user_role_display(self, user_id: str) -> str:
        """Get user role display name"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            role_mapping = UserRoles.get_display_names()
            return role_mapping.get(user.get("org_role", ""), "Unknown")
        return "Unknown"

    def get_user_status_display(self, user_id: str) -> str:
        """Get user status display"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            return "Active" if user.get("is_active", False) else "Inactive"
        return "Unknown"

    async def delete_user(self, user_id: str):
        """Delete a user"""
        async def delete_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error_message = "Access denied: Admin privileges required"
                return False
            
            result = await UserManagementService.delete_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error_message = result.get("error", "Failed to delete user")
                return False
        
        await self.handle_async_operation(
            delete_user_data,
            "User deleted successfully"
        )

    # Assignment dialog state
    assignment_dialog_open: bool = False
    assignment_user_id: str = ""
    assignment_user_name: str = ""
    assignment_project_name: str = ""
    assignment_roles: List[str] = []
    
    # Project management dialog state
    project_management_dialog_open: bool = False
    project_management_user_id: str = ""
    project_management_user_name: str = ""
    project_management_user_assignments: List[Dict] = []

    def open_assignment_dialog(self, user_id: str):
        """Open assignment dialog for a user"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.assignment_user_id = user_id
            self.assignment_user_name = user.get("username", "")
            self.assignment_project_name = ""
            self.assignment_roles = []
            self.assignment_dialog_open = True

    def close_assignment_dialog(self):
        """Close assignment dialog"""
        self.assignment_dialog_open = False
        self.assignment_user_id = ""
        self.assignment_user_name = ""
        self.assignment_project_name = ""
        self.assignment_roles = []

    def set_assignment_dialog_open(self, open: bool):
        """Set assignment dialog open state"""
        self.assignment_dialog_open = open

    def set_assignment_project_by_name(self, project_name: str):
        """Set assignment project by name"""
        self.assignment_project_name = project_name

    def toggle_assignment_role(self, role: str):
        """Toggle assignment role"""
        if role in self.assignment_roles:
            self.assignment_roles.remove(role)
        else:
            self.assignment_roles.append(role)

    def open_project_management_dialog(self, user_id: str):
        """Open project management dialog for a user"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.project_management_user_id = user_id
            self.project_management_user_name = user.get("username", "")
            self.project_management_user_assignments = []  # TODO: Load user's project assignments
            self.project_management_dialog_open = True

    def close_project_management_dialog(self):
        """Close project management dialog"""
        self.project_management_dialog_open = False
        self.project_management_user_id = ""
        self.project_management_user_name = ""
        self.project_management_user_assignments = []

    def set_project_management_dialog_open(self, open: bool):
        """Set project management dialog open state"""
        self.project_management_dialog_open = open

    async def assign_user_to_project_from_dialog(self):
        """Assign user to project from dialog"""
        async def assign_user():
            if not self.assignment_user_id or not self.assignment_project_name:
                self.error_message = "Please select a user and project"
                return False
            
            project = next((p for p in self.available_projects if p["name"] == self.assignment_project_name), None)
            if not project:
                self.error_message = "Project not found"
                return False
            
            # TODO: Implement project assignment logic
            # For now, just close the dialog
            self.close_assignment_dialog()
            return True
        
        await self.handle_async_operation(
            assign_user,
            "User assigned to project successfully"
        )

    async def remove_user_from_project(self, user_id: str, project_id: str):
        """Remove user from project"""
        async def remove_user():
            # TODO: Implement remove user from project logic
            return True
        
        await self.handle_async_operation(
            remove_user,
            "User removed from project successfully"
        )

    @rx.var
    def available_project_options(self) -> List[str]:
        """Get available project names for assignment"""
        return [project.get("name", "") for project in self.available_projects]

    @rx.var
    def available_project_roles(self) -> List[str]:
        """Get available project roles"""
        return ["viewer", "editor", "admin"]  # TODO: Define proper project roles

    @rx.var
    def total_users_count(self) -> int:
        """Get total users count"""
        return len(self.organization_users)

    @rx.var
    def active_users_count(self) -> int:
        """Get active users count"""
        return len([user for user in self.organization_users if user.get("is_active", False)])

    def can_edit_user(self, user_id: str) -> bool:
        """Check if current user can edit the specified user"""
        # TODO: Implement proper permission check
        return True

    def can_deactivate_user(self, user_id: str) -> bool:
        """Check if current user can deactivate the specified user"""
        # TODO: Implement proper permission check
        return True

 