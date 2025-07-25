import reflex as rx
from typing import List, Dict, Optional
from poseidon.backend.services.user_management_service import UserManagementService
from poseidon.backend.database.models.enums import OrgRole
from poseidon.state.base import BasePaginationState, RoleBasedAccessMixin
from poseidon.state.models import UserRoles


class UserManagementState(BasePaginationState, RoleBasedAccessMixin):
    """User management state with role-based access control."""
    
    # User list and filtering
    organization_users: List[Dict] = []
    filtered_users: List[Dict] = []
    role_filter: str = ""
    
    # Add user form
    new_user_username: str = ""
    new_user_email: str = ""
    new_user_role: str = ""
    add_user_dialog_open: bool = False
    
    # Edit user form
    edit_user_id: str = ""
    edit_user_username: str = ""
    edit_user_email: str = ""
    edit_user_role: str = ""
    edit_user_dialog_open: bool = False
    
    # User details
    selected_user: Dict = {}
    user_details_dialog_open: bool = False
    
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
    
    # Available projects for assignment
    available_projects: List[Dict] = []
    
    # --- Computed Properties ---
    @rx.var
    def total_pages(self) -> int:
        """Calculate total number of pages for filtered users"""
        return self.calculate_total_pages(self.filtered_users)
    
    @rx.var
    def paginated_users(self) -> List[Dict]:
        """Get users for current page"""
        return self.get_paginated_items(self.filtered_users)
    
    @rx.var
    def available_org_roles(self) -> List[str]:
        """Get available organization roles based on user permissions"""
        roles = [UserRoles.USER]
        # Only admins and super admins can assign admin roles
        # This will be checked in the actual assignment
        roles.append(UserRoles.ADMIN)
        return roles
    
    @rx.var
    def available_project_options(self) -> List[str]:
        """Get available project names for assignment"""
        return [project.get("name", "") for project in self.available_projects]
    
    @rx.var
    def available_project_roles(self) -> List[str]:
        """Get available project roles"""
        return ["viewer", "editor", "admin"]
    
    @rx.var
    def total_users_count(self) -> int:
        """Get total users count"""
        return len(self.organization_users)
    
    @rx.var
    def active_users_count(self) -> int:
        """Get active users count"""
        return len([user for user in self.organization_users if user.get("is_active", False)])
    
    @rx.var
    def edit_user_role_options(self) -> List[str]:
        """Get available organization roles for edit form"""
        return self.available_org_roles

    # --- Data Loading Methods ---
    async def load_organization_users(self):
        """Load users based on user role - all users for super admin, org users for admin"""
        async def load_users():
            auth_state = await self.get_auth_state()
            
            if auth_state.is_super_admin:
                # Super admin sees all users across all organizations
                from poseidon.backend.database.repositories.user_repository import UserRepository
                users = await UserRepository.get_all_users()
                
                # Only fetch organization links for better performance
                for user in users:
                    if user.organization:
                        await user.fetch_link("organization")
                
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
                from poseidon.backend.database.repositories.user_repository import UserRepository
                users = await UserRepository.get_by_organization(auth_state.user_organization_id)
            
            for user in users:
                    if user.organization:
                        await user.fetch_link("organization")
                
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
            
            self.filter_users()
            return True

        await self.handle_async_operation(load_users, "Users loaded successfully")

    async def load_available_projects(self):
        """Load available projects for assignment"""
        async def load_projects():
            auth_state = await self.get_auth_state()
            org_id = auth_state.user_organization_id
            
            if not org_id:
                return False
            
            from poseidon.backend.database.repositories.project_repository import ProjectRepository
            
            if auth_state.is_super_admin:
                # Super admin can see all projects across all organizations
                projects = await ProjectRepository.get_all()
            else:
                # Admin can see projects in their organization
                projects = await ProjectRepository.get_by_organization(org_id)
            
            # Fetch organization links for projects
            for project in projects:
                if not hasattr(project, '_organization_loaded'):
                    await project.fetch_link("organization")
                    project._organization_loaded = True
                
            self.available_projects = [
                {
                    "id": str(project.id),
                    "name": project.name,
                    "organization_id": str(project.organization.id) if project.organization else "",
                    "organization_name": project.organization.name if project.organization else "Unknown"
                }
                for project in projects
            ]
            return True
            
        await self.handle_async_operation(load_projects, "Projects loaded successfully")

    # --- Filtering Methods ---
    def filter_users(self):
        """Filter users based on search query and filters"""
        filtered = self.organization_users
        
        # Search filter
        if self.search_query:
            filtered = [
                user for user in filtered
                if (self.search_query.lower() in user.get("username", "").lower() or
                    self.search_query.lower() in user.get("email", "").lower())
            ]
        
        # Role filter
        if self.role_filter:
            filtered = [
                user for user in filtered
                if self.role_filter == user.get("org_role", "")
            ]
        
        # Status filter
        if self.status_filter == "active":
                filtered = [user for user in filtered if user.get("is_active", False)]
        elif self.status_filter == "inactive":
                filtered = [user for user in filtered if not user.get("is_active", False)]
        
        self.filtered_users = filtered
        # Reset to first page when filtering
        self.current_page = 1

    def set_search_query(self, query: str):
        """Set search query and filter users"""
        self.search_query = query
        self.filter_users()

    def set_role_filter(self, role: str):
        """Set role filter and filter users"""
        self.role_filter = role
        self.filter_users()

    def set_status_filter(self, status: str):
        """Set status filter and filter users"""
        self.status_filter = status
        self.filter_users()

    def clear_filters(self):
        """Clear all filters"""
        super().clear_filters()
        self.role_filter = ""
        self.filter_users()

    # --- Dialog Management Methods ---
    def open_add_user_dialog(self):
        """Open add user dialog"""
        self.add_user_dialog_open = True
        self.clear_messages()
        self.clear_add_user_form()

    def close_add_user_dialog(self):
        """Close add user dialog"""
        self.add_user_dialog_open = False
        self.clear_messages()
        self.clear_add_user_form()

    def open_edit_user_dialog(self, user_id: str):
        """Open edit user dialog"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.edit_user_id = user_id
            self.edit_user_username = user.get("username", "")
            self.edit_user_email = user.get("email", "")
            self.edit_user_role = user.get("org_role", "")
            self.edit_user_dialog_open = True
            self.clear_messages()

    def close_edit_user_dialog(self):
        """Close edit user dialog"""
        self.edit_user_dialog_open = False
        self.clear_messages()
        self.clear_edit_user_form()

    def open_user_details_dialog(self, user_id: str):
        """Open user details dialog"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.selected_user = user
            self.user_details_dialog_open = True
            self.clear_messages()

    def close_user_details_dialog(self):
        """Close user details dialog"""
        self.user_details_dialog_open = False
        self.clear_messages()
        self.selected_user = {}

    def open_assignment_dialog(self, user_id: str):
        """Open assignment dialog for a user"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.assignment_user_id = user_id
            self.assignment_user_name = user.get("username", "")
            self.assignment_project_name = ""
            self.assignment_roles = []
            self.assignment_dialog_open = True
            self.clear_messages()

    def close_assignment_dialog(self):
        """Close assignment dialog"""
        self.assignment_dialog_open = False
        self.clear_messages()
        self.assignment_user_id = ""
        self.assignment_user_name = ""
        self.assignment_project_name = ""
        self.assignment_roles = []

    async def load_projects_for_assignment(self):
        """Load projects for assignment dialog - called from UI"""
        await self.load_available_projects()

    async def open_project_management_dialog(self, user_id: str):
        """Open project management dialog for a user"""
        user = next((u for u in self.organization_users if u["id"] == user_id), None)
        if user:
            self.project_management_user_id = user_id
            self.project_management_user_name = user.get("username", "")
            
            # Load user's project assignments
            try:
                from poseidon.backend.database.repositories.user_repository import UserRepository
                user_obj = await UserRepository.get_by_id(user_id)
                if user_obj:
                    await user_obj.fetch_all_links()
                    self.project_management_user_assignments = [
                        {
                            "project_id": str(project.id),
                            "project_name": project.name,
                            "roles": ["user"]  # Default role for now
                        }
                        for project in user_obj.projects
                    ]
                else:
                    self.project_management_user_assignments = []
            except Exception as e:
                self.set_error(f"Failed to load user project assignments: {str(e)}")
                self.project_management_user_assignments = []
            
            self.project_management_dialog_open = True
            self.clear_messages()

    def close_project_management_dialog(self):
        """Close project management dialog"""
        self.project_management_dialog_open = False
        self.clear_messages()
        self.project_management_user_id = ""
        self.project_management_user_name = ""
        self.project_management_user_assignments = []

    # --- Form Management Methods ---
    def clear_add_user_form(self):
        """Clear add user form"""
        self.new_user_username = ""
        self.new_user_email = ""
        self.new_user_role = ""

    def clear_edit_user_form(self):
        """Clear edit user form"""
        self.edit_user_id = ""
        self.edit_user_username = ""
        self.edit_user_email = ""
        self.edit_user_role = ""

    # --- Assignment Methods ---
    def set_assignment_project_by_name(self, project_name: str):
        """Set assignment project by name"""
        self.assignment_project_name = project_name

    def set_edit_user_data(self, user_data: dict):
        """Set edit user data from user dictionary"""
        self.edit_user_id = user_data.get("id", "")
        self.edit_user_username = user_data.get("username", "")
        self.edit_user_email = user_data.get("email", "")
        self.edit_user_role = user_data.get("org_role", "")

    def toggle_assignment_role(self, role: str):
        """Toggle assignment role"""
        if role in self.assignment_roles:
            self.assignment_roles.remove(role)
        else:
            self.assignment_roles.append(role)

    # --- CRUD Operations ---
    async def add_user(self):
        """Add a new user to the organization"""
        async def create_user():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.set_error("Access denied: Admin privileges required")
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
            reverse_role_mapping = {v: k for k, v in role_mapping.items()}
            reverse_role_mapping.update({k: k for k in UserRoles.get_assignable()})
            
            backend_role = reverse_role_mapping.get(self.new_user_role, UserRoles.USER)
            
            # Validate role assignment permissions
            auth_state = await self.get_auth_state()
            if backend_role == UserRoles.ADMIN and not self.can_manage_users(auth_state.is_admin, auth_state.is_super_admin):
                self.set_error("Only admins can assign admin role")
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
                self.close_add_user_dialog()
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to add user"))
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
                self.set_error("Access denied: Admin privileges required")
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
                self.set_error("Only admins can assign admin role")
                return False
            
            # Update user organization role
            result = await UserManagementService.update_user_org_role(
                self.edit_user_id,
                self.edit_user_role,
                org_id
            )
            
            if result.get("success"):
                self.clear_edit_user_form()
                self.close_edit_user_dialog()
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to update user"))
                return False
        
        await self.handle_async_operation(
            update_user_data,
            "User updated successfully"
        )

    async def activate_user(self, user_id: str):
        """Activate a user"""
        async def activate_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            result = await UserManagementService.activate_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to activate user"))
                return False
        
        await self.handle_async_operation(
            activate_user_data,
            "User activated successfully"
        )

    async def deactivate_user(self, user_id: str):
        """Deactivate a user"""
        async def deactivate_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            result = await UserManagementService.deactivate_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to deactivate user"))
                return False

        await self.handle_async_operation(
            deactivate_user_data,
            "User deactivated successfully"
        )

    async def delete_user(self, user_id: str):
        """Delete a user"""
        async def delete_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            result = await UserManagementService.delete_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to delete user"))
                return False
        
        await self.handle_async_operation(
            delete_user_data,
            "User deleted successfully"
        )

    async def assign_user_to_project_from_dialog(self):
        """Assign user to project from dialog"""
        async def assign_user():
            if not self.assignment_user_id or not self.assignment_project_name:
                self.set_error("Please select a user and project")
                return False
            
            project = next((p for p in self.available_projects if p["name"] == self.assignment_project_name), None)
            if not project:
                self.set_error("Project not found")
                return False
            
            # Get admin organization ID
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # Call the user management service to assign user to project
            result = await UserManagementService.assign_user_to_project(
                user_id=self.assignment_user_id,
                project_id=project["id"],
                roles=self.assignment_roles if self.assignment_roles else ["user"],
                admin_organization_id=org_id
            )
            
            if result.get("success"):
                self.close_assignment_dialog()
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to assign user to project"))
                return False
        
        await self.handle_async_operation(
            assign_user,
            "User assigned to project successfully"
        )

    async def remove_user_from_project(self, user_id: str, project_id: str):
        """Remove user from project"""
        async def remove_user():
            # Get admin organization ID
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # Call the user management service to remove user from project
            result = await UserManagementService.remove_user_from_project(
                user_id=user_id,
                project_id=project_id,
                admin_organization_id=org_id
            )
            
            if result.get("success"):
                await self.load_organization_users()
                return True
            else:
                self.set_error(result.get("error", "Failed to remove user from project"))
                return False
        
        await self.handle_async_operation(
            remove_user,
            "User removed from project successfully"
        )

    # --- Utility Methods ---
    def can_edit_user(self, user_id: str) -> bool:
        """Check if current user can edit the specified user"""
        # TODO: Implement proper permission check
        return True

    def can_deactivate_user(self, user_id: str) -> bool:
        """Check if current user can deactivate the specified user"""
        # TODO: Implement proper permission check
        return True

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

 