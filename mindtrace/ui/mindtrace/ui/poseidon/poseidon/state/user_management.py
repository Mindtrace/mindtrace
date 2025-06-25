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

    def clear_messages(self):
        """Clear success and error messages"""
        self.error = ""
        self.success = ""

    async def get_admin_organization_id(self) -> Optional[str]:
        """Get the organization ID of the current admin user"""
        auth_state = await self.get_state(AuthState)
        if auth_state.is_authenticated and auth_state.is_admin:
            return auth_state.user_organization_id
        return None

    async def load_organization_users(self):
        """Load all users in the current organization"""
        try:
            self.loading = True
            self.clear_messages()
            
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
            
        except Exception as e:
            self.error = f"Failed to load users: {str(e)}"
        finally:
            self.loading = False

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
        """Get list of available organization roles"""
        return ["member", "org_admin", "viewer"]

    @rx.var
    def available_project_roles(self) -> List[str]:
        """Get list of available project roles"""
        return ["project_manager", "inspector", "analyst", "viewer"] 