import reflex as rx
from poseidon.backend.services.user_management_service import UserManagementService
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.state.auth import AuthState
from typing import List, Dict, Optional

class UserManagementState(rx.State):
    # UI State
    error: str = ""
    success: str = ""
    loading: bool = False
    
    # User Management Data
    organization_users: List[Dict] = []
    project_users: List[Dict] = []
    
    # Filters and Search
    search_query: str = ""
    role_filter: str = ""
    status_filter: str = "active"  # active, inactive, all
    
    # Add User Form Data
    new_user_username: str = ""
    new_user_email: str = ""
    new_user_role: str = ""

    # Edit User Form Data
    edit_user_id: str = ""
    edit_user_username: str = ""
    edit_user_email: str = ""
    edit_user_role: str = ""

    def clear_messages(self):
        """Clear success and error messages"""
        self.error = ""
        self.success = ""

    async def get_admin_organization_id(self) -> Optional[str]:
        """Get the organization ID of the current admin user"""
        auth_state = await self.get_state(AuthState)
        if auth_state.is_authenticated and (auth_state.is_admin or auth_state.is_super_admin):
            return auth_state.user_organization_id
        return None

    async def load_organization_users(self):
        """Load users based on user role - all users for super admin, org users for admin"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            
            if auth_state.is_super_admin:
                # Super admin sees all users across all organizations
                await self.load_all_users()
            elif auth_state.is_admin:
                # Regular admin sees only their organization users
                await self.load_admin_organization_users()
            else:
                self.error = "Access denied: Admin privileges required"
                return
            
        except Exception as e:
            self.error = f"Failed to load users: {str(e)}"
        finally:
            self.loading = False

    async def load_all_users(self):
        """Load all users across all organizations (super admin only)"""
        users = await UserManagementService.get_all_users()
        self.organization_users = [
            {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "org_roles": user.org_roles,
                "project_assignments": user.project_assignments,
                "is_active": user.is_active,
                "organization_id": user.organization_id,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            for user in users
        ]

    async def load_admin_organization_users(self):
        """Load users in admin's organization only"""
        org_id = await self.get_admin_organization_id()
        if not org_id:
            self.error = "Access denied: Admin privileges required"
            return
        
        users = await UserManagementService.get_organization_users(org_id)
        self.organization_users = [
            {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "org_roles": user.org_roles,
                "project_assignments": user.project_assignments,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            for user in users
        ]

    async def load_project_users(self, project_id: str):
        """Load all users assigned to a specific project"""
        try:
            self.loading = True
            self.clear_messages()
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return
            
            users = await UserManagementService.get_project_users(project_id, org_id)
            self.project_users = [
                {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "project_roles": user.get_user_project_roles(project_id) if hasattr(user, 'get_user_project_roles') else [],
                    "is_active": user.is_active
                }
                for user in users
            ]
            
        except Exception as e:
            self.error = f"Failed to load project users: {str(e)}"
        finally:
            self.loading = False

    async def assign_user_to_project(self, form_data: Dict):
        """Assign a user to a project with specific roles"""
        try:
            self.loading = True
            self.clear_messages()
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return
            
            user_id = form_data.get("user_id")
            project_id = form_data.get("project_id")
            roles = form_data.get("roles", [])
            
            if not user_id or not project_id:
                self.error = "User and project are required"
                return
                
            if not roles:
                self.error = "At least one role is required"
                return
            
            result = await UserManagementService.assign_user_to_project(
                user_id, project_id, roles, org_id
            )
            
            if result.get("success"):
                self.success = f"User successfully assigned to project"
                await self.load_organization_users()  # Refresh user list
            
        except Exception as e:
            self.error = f"Failed to assign user to project: {str(e)}"
        finally:
            self.loading = False

    async def remove_user_from_project(self, user_id: str, project_id: str):
        """Remove a user from a project"""
        try:
            self.loading = True
            self.clear_messages()
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return
            
            result = await UserManagementService.remove_user_from_project(
                user_id, project_id, org_id
            )
            
            if result.get("success"):
                self.success = "User successfully removed from project"
                await self.load_organization_users()  # Refresh user list
            
        except Exception as e:
            self.error = f"Failed to remove user from project: {str(e)}"
        finally:
            self.loading = False

    async def update_user_org_roles(self, form_data: Dict):
        """Update a user's organization roles"""
        try:
            self.loading = True
            self.clear_messages()
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return
            
            user_id = form_data.get("user_id")
            roles = form_data.get("roles", [])
            
            if not user_id:
                self.error = "User is required"
                return
                
            if not roles:
                self.error = "At least one role is required"
                return
            
            result = await UserManagementService.update_user_org_roles(
                user_id, roles, org_id
            )
            
            if result.get("success"):
                self.success = "User roles updated successfully"
                await self.load_organization_users()  # Refresh user list
            
        except Exception as e:
            self.error = f"Failed to update user roles: {str(e)}"
        finally:
            self.loading = False

    async def deactivate_user(self, user_id: str):
        """Deactivate a user account"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if auth_state.is_super_admin:
                org_id = None
            else:
                org_id = await self.get_admin_organization_id()
                if not org_id:
                    self.error = "Access denied: Admin privileges required"
                    return
            
            result = await UserManagementService.deactivate_user(user_id, org_id)
            
            if result.get("success"):
                self.success = "User deactivated successfully"
                await self.load_organization_users()  # Refresh user list
            
        except Exception as e:
            self.error = f"Failed to deactivate user: {str(e)}"
        finally:
            self.loading = False

    async def activate_user(self, user_id: str):
        """Activate a user account"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if auth_state.is_super_admin:
                org_id = None
            else:
                org_id = await self.get_admin_organization_id()
                if not org_id:
                    self.error = "Access denied: Admin privileges required"
                    return
            
            result = await UserManagementService.activate_user(user_id, org_id)
            
            if result.get("success"):
                self.success = "User activated successfully"
                await self.load_organization_users()  # Refresh user list
            
        except Exception as e:
            self.error = f"Failed to activate user: {str(e)}"
        finally:
            self.loading = False

    async def check_user_permission(self, user_id: str, project_id: Optional[str] = None, 
                                   required_org_role: Optional[str] = None,
                                   required_project_role: Optional[str] = None):
        """Check if a user has required permissions"""
        try:
            result = await UserManagementService.check_user_permission(
                user_id, project_id, required_org_role, required_project_role
            )
            return result
            
        except Exception as e:
            self.error = f"Failed to check permissions: {str(e)}"
            return {"has_permission": False, "reason": str(e)}

    @rx.var
    def filtered_users(self) -> List[Dict]:
        """Get filtered list of organization users"""
        users = self.organization_users
        
        # Filter by search query
        if self.search_query:
            users = [
                user for user in users
                if (self.search_query.lower() in user.get("username", "").lower() or
                    self.search_query.lower() in user.get("email", "").lower())
            ]
        
        # Filter by role
        if self.role_filter and self.role_filter != "all_roles":
            users = [
                user for user in users
                if self.role_filter in user.get("org_roles", [])
            ]
        
        # Filter by status
        if self.status_filter == "active":
            users = [user for user in users if user.get("is_active", False)]
        elif self.status_filter == "inactive":
            users = [user for user in users if not user.get("is_active", True)]
        # "all" shows all users
        
        return users

    @rx.var
    def available_org_roles(self) -> List[str]:
        """Get list of available organization roles (no super_admin assignment)"""
        return ["user", "admin"]
    
    @rx.var
    def available_display_roles(self) -> List[str]:
        """Get list of available roles for display in add user popup (no Super Admin)"""
        return ["User", "Admin"]
    
    @rx.var
    def edit_user_role_options(self) -> List[str]:
        """Get role options for editing users (no super_admin assignment)"""
        return ["user", "admin"]

    @rx.var
    def available_project_roles(self) -> List[str]:
        """Get list of available project roles"""
        return ["project_manager", "inspector", "analyst", "viewer"]
    
    def can_edit_user(self, target_user_id: str) -> bool:
        """Check if current user can edit the target user"""
        # No one can edit themselves (self-protection)
        if AuthState.user_id == target_user_id:
            return False
            
        # Super admins can edit anyone except themselves
        if AuthState.is_super_admin:
            return True
            
        # Regular admins can edit other users except themselves
        if AuthState.is_admin:
            return True
            
        # Regular users cannot edit anyone
        return False
    
    def can_deactivate_user(self, target_user_id: str) -> bool:
        """Check if current user can deactivate the target user"""
        # No one can deactivate themselves (self-protection)
        if AuthState.user_id == target_user_id:
            return False
            
        # Super admins can deactivate anyone except themselves
        if AuthState.is_super_admin:
            return True
            
        # Regular admins can deactivate other users except themselves
        if AuthState.is_admin:
            return True
            
        # Regular users cannot deactivate anyone
        return False

    def clear_new_user_form(self):
        """Clear the new user form data"""
        self.new_user_username = ""
        self.new_user_email = ""
        self.new_user_role = ""

    async def add_user(self):
        """Add a new user to the organization"""
        try:
            self.loading = True
            self.clear_messages()
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return
            
            # Validate form data
            if not self.new_user_username.strip():
                self.error = "Username is required"
                return
                
            if not self.new_user_email.strip():
                self.error = "Email is required"
                return
                
            if not self.new_user_role:
                self.error = "Role is required"
                return
            
            # Convert role to unified format
            role_mapping = {
                "User": "user",
                "Admin": "admin", 
                # Direct role names (no conversion needed)
                "user": "user",
                "admin": "admin"
            }
            
            backend_role = role_mapping.get(self.new_user_role, "user")
            
            # Validate role assignment permissions
            auth_state = await self.get_state(AuthState)
            if backend_role == "admin" and not (auth_state.is_admin or auth_state.is_super_admin):
                self.error = "Only admins can assign admin role"
                return
            
            # Call user management service to add user
            result = await UserManagementService.create_user_in_organization(
                username=self.new_user_username.strip(),
                email=self.new_user_email.strip(),
                password="TempPassword123!",  # TODO: Generate secure temp password
                admin_organization_id=org_id,
                org_roles=[backend_role]
            )
            
            if result.get("success"):
                self.success = f"User '{self.new_user_username}' added successfully"
                self.clear_new_user_form()
                await self.load_organization_users()  # Refresh user list
            else:
                self.error = result.get("error", "Failed to add user")
            
        except Exception as e:
            self.error = f"Failed to add user: {str(e)}"
        finally:
            self.loading = False

    def set_edit_user_data(self, user_data: Dict):
        """Set edit user form data from selected user"""
        self.edit_user_id = user_data.get("id", "")
        self.edit_user_username = user_data.get("username", "")
        self.edit_user_email = user_data.get("email", "")
        # Set role using unified naming
        org_roles = user_data.get("org_roles", [])
        if "super_admin" in org_roles:
            self.edit_user_role = "super_admin"
        elif "admin" in org_roles:
            self.edit_user_role = "admin"
        else:
            self.edit_user_role = "user"

    def clear_edit_user_form(self):
        """Clear the edit user form data"""
        self.edit_user_id = ""
        self.edit_user_username = ""
        self.edit_user_email = ""
        self.edit_user_role = ""

    async def update_user(self):
        """Update an existing user"""
        try:
            self.loading = True
            self.clear_messages()
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return
            
            # Validate form data
            if not self.edit_user_username.strip():
                self.error = "Username is required"
                return
                
            if not self.edit_user_email.strip():
                self.error = "Email is required"
                return
                
            if not self.edit_user_role:
                self.error = "Role is required"
                return
            
            # Validate role assignment permissions
            auth_state = await self.get_state(AuthState)
            if self.edit_user_role == "admin" and not (auth_state.is_admin or auth_state.is_super_admin):
                self.error = "Only admins can assign admin role"
                return
            
            # Update user organization roles
            result = await UserManagementService.update_user_org_roles(
                self.edit_user_id,
                [self.edit_user_role],
                org_id
            )
            
            if result.get("success"):
                self.success = f"User '{self.edit_user_username}' updated successfully"
                self.clear_edit_user_form()
                await self.load_organization_users()  # Refresh user list
            else:
                self.error = result.get("error", "Failed to update user")
            
        except Exception as e:
            self.error = f"Failed to update user: {str(e)}"
        finally:
            self.loading = False 