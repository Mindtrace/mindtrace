import reflex as rx
from poseidon.backend.services.user_management_service import UserManagementService
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.state.base import BaseDialogState, RoleBasedAccessMixin
from poseidon.state.models import UserData, ProjectData, UserRoles, ProjectRoles, StatusTypes
from poseidon.state.auth import AuthState
from typing import List, Dict, Optional

class UserManagementState(BaseDialogState, RoleBasedAccessMixin):
    """State management for user administration operations."""
    
    # User Management Data
    organization_users: List[Dict] = []
    project_users: List[Dict] = []
    available_projects: List[Dict] = []  # Projects available for assignment
    
    # Additional Filters (extends BaseFilterState)
    role_filter: str = ""
    
    # Add User Form Data
    new_user_username: str = ""
    new_user_email: str = ""
    new_user_role: str = ""

    # Edit User Form Data
    edit_user_id: str = ""
    edit_user_username: str = ""
    edit_user_email: str = ""
    edit_user_role: str = ""

    # Project Assignment Form Data
    assignment_user_id: str = ""
    assignment_project_id: str = ""
    assignment_roles: List[str] = []
    assignment_dialog_open: bool = False
    
    # Project Management Dialog Data
    project_management_user_id: str = ""
    project_management_dialog_open: bool = False

    async def load_available_projects(self):
        """Load projects available for assignment"""
        try:
            auth_state = await self.get_auth_state()
            if not auth_state.is_authenticated:
                return
            
            if auth_state.is_super_admin:
                # Super admins can see all active projects across all organizations
                projects = await ProjectRepository.get_all()
                # Filter to only active projects
                projects = [p for p in projects if p.status == "active"]
            else:
                # Regular admins only see projects in their organization
                org_id = await self.get_admin_organization_id()
                if not org_id:
                    return
                projects = await ProjectRepository.get_by_organization_and_status(org_id, "active")
            
            self.available_projects = [
                {
                    "id": str(project.id),
                    "name": project.name,
                    "description": project.description or "",
                    "status": project.status if hasattr(project, 'status') else "active",
                    "organization_id": project.organization_id
                }
                for project in projects
            ]
            
        except Exception as e:
            self.error = f"Failed to load projects: {str(e)}"

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
                        "organization_id": user.organization_id,
                        "org_roles": user.org_roles,
                        "project_assignments": user.project_assignments,
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
        async def load_project_users_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return False
            
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
            return True
        
        await self.handle_async_operation(
            load_project_users_data,
            "Project users loaded successfully"
        )

    async def assign_user_to_project(self, form_data: Dict):
        """Assign a user to a project with specific roles"""
        async def assign_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return False
            
            user_id = form_data.get("user_id")
            project_id = form_data.get("project_id")
            roles = form_data.get("roles", [])
            
            if not user_id or not project_id:
                self.error = "User and project are required"
                return False
                
            if not roles:
                self.error = "At least one role is required"
                return False
            
            result = await UserManagementService.assign_user_to_project(
                user_id, project_id, roles, org_id
            )
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            return False
        
        await self.handle_async_operation(
            assign_user_data,
            "User successfully assigned to project"
        )

    async def remove_user_from_project(self, user_id: str, project_id: str):
        """Remove user from a project"""
        async def remove_user_data():
            # Get the user
            user = await UserRepository.get_by_id(user_id)
            if not user:
                self.error = "User not found"
                return False
            
            # Remove project assignment
            user.remove_project_assignment(project_id)
            
            # Update user in database
            await UserRepository.update(user_id, {
                "project_assignments": user.project_assignments
            })
            
            await self.load_organization_users()  # Refresh user list
            return True
        
        await self.handle_async_operation(
            remove_user_data,
            "User removed from project successfully"
        )

    async def update_user_org_roles(self, form_data: Dict):
        """Update a user's organization roles"""
        async def update_roles_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return False
            
            user_id = form_data.get("user_id")
            roles = form_data.get("roles", [])
            
            if not user_id:
                self.error = "User is required"
                return False
                
            if not roles:
                self.error = "At least one role is required"
                return False
            
            result = await UserManagementService.update_user_org_roles(
                user_id, roles, org_id
            )
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            return False
        
        await self.handle_async_operation(
            update_roles_data,
            "User roles updated successfully"
        )

    async def deactivate_user(self, user_id: str):
        """Deactivate a user account"""
        async def deactivate_user_data():
            auth_state = await self.get_auth_state()
            if auth_state.is_super_admin:
                org_id = None
            else:
                org_id = await self.get_admin_organization_id()
                if not org_id:
                    self.error = "Access denied: Admin privileges required"
                    return False
            
            result = await UserManagementService.deactivate_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            return False
        
        await self.handle_async_operation(
            deactivate_user_data,
            "User deactivated successfully"
        )

    async def activate_user(self, user_id: str):
        """Activate a user account"""
        async def activate_user_data():
            auth_state = await self.get_auth_state()
            if auth_state.is_super_admin:
                org_id = None
            else:
                org_id = await self.get_admin_organization_id()
                if not org_id:
                    self.error = "Access denied: Admin privileges required"
                    return False
            
            result = await UserManagementService.activate_user(user_id, org_id)
            
            if result.get("success"):
                await self.load_organization_users()  # Refresh user list
                return True
            return False
        
        await self.handle_async_operation(
            activate_user_data,
            "User activated successfully"
        )

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
        
        # Apply search filter
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
        
        # Apply status filter
        if self.status_filter == StatusTypes.ACTIVE:
            users = [user for user in users if user.get("is_active", False)]
        elif self.status_filter == StatusTypes.INACTIVE:
            users = [user for user in users if not user.get("is_active", True)]
        # "all" shows all users
        
        return users

    @rx.var
    def available_org_roles(self) -> List[str]:
        """Get list of available organization roles (no super_admin assignment)"""
        return UserRoles.get_assignable()
    
    @rx.var
    def available_display_roles(self) -> List[str]:
        """Get list of available roles for display in add user popup (no Super Admin)"""
        return [UserRoles.get_display_names()[role] for role in UserRoles.get_assignable()]
    
    @rx.var
    def edit_user_role_options(self) -> List[str]:
        """Get role options for editing users (no super_admin assignment)"""
        return UserRoles.get_assignable()

    @rx.var
    def available_project_roles(self) -> List[str]:
        """Get list of available project roles"""
        return ProjectRoles.get_all()
    
    def can_edit_user(self, target_user_id: str) -> bool:
        """Check if current user can edit the target user"""
        from poseidon.state.auth import AuthState
        return self.can_edit_item(target_user_id, AuthState.user_id, AuthState.is_admin, AuthState.is_super_admin)
    
    def can_deactivate_user(self, target_user_id: str) -> bool:
        """Check if current user can deactivate the target user"""
        from poseidon.state.auth import AuthState
        return self.can_deactivate_item(target_user_id, AuthState.user_id, AuthState.is_admin, AuthState.is_super_admin)

    def clear_new_user_form(self):
        """Clear the new user form data"""
        self.new_user_username = ""
        self.new_user_email = ""
        self.new_user_role = ""

    async def add_user(self):
        """Add a new user to the organization"""
        async def create_user():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
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
                self.error = "Only admins can assign admin role"
                return False
            
            # Call user management service to add user
            result = await UserManagementService.create_user_in_organization(
                username=self.new_user_username.strip(),
                email=self.new_user_email.strip(),
                password="TempPassword123!",  # TODO: Generate secure temp password
                admin_organization_id=org_id,
                org_roles=[backend_role]
            )
            
            if result.get("success"):
                self.clear_new_user_form()
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error = result.get("error", "Failed to add user")
                return False
        
        await self.handle_async_operation(
            create_user,
            f"User '{self.new_user_username}' added successfully"
        )

    def set_edit_user_data(self, user_data: Dict):
        """Set edit user form data from selected user"""
        self.edit_user_id = user_data.get("id", "")
        self.edit_user_username = user_data.get("username", "")
        self.edit_user_email = user_data.get("email", "")
        # Set role using unified naming
        org_roles = user_data.get("org_roles", [])
        if UserRoles.SUPER_ADMIN in org_roles:
            self.edit_user_role = UserRoles.SUPER_ADMIN
        elif UserRoles.ADMIN in org_roles:
            self.edit_user_role = UserRoles.ADMIN
        else:
            self.edit_user_role = UserRoles.USER

    def clear_edit_user_form(self):
        """Clear the edit user form data"""
        self.edit_user_id = ""
        self.edit_user_username = ""
        self.edit_user_email = ""
        self.edit_user_role = ""

    async def update_user(self):
        """Update an existing user"""
        async def update_user_data():
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
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
                self.error = "Only admins can assign admin role"
                return False
            
            # Update user organization roles
            result = await UserManagementService.update_user_org_roles(
                self.edit_user_id,
                [self.edit_user_role],
                org_id
            )
            
            if result.get("success"):
                self.clear_edit_user_form()
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error = result.get("error", "Failed to update user")
                return False
        
        await self.handle_async_operation(
            update_user_data,
            f"User '{self.edit_user_username}' updated successfully"
        )

    # Project Assignment Methods
    async def open_assignment_dialog(self, user_id: str):
        """Open project assignment dialog for a specific user"""
        self.assignment_user_id = user_id
        self.assignment_project_id = ""
        self.assignment_roles = []
        self.assignment_dialog_open = True
        # Load available projects for the organization
        await self.load_available_projects()

    def close_assignment_dialog(self):
        """Close project assignment dialog"""
        self.assignment_user_id = ""
        self.assignment_project_id = ""
        self.assignment_roles = []
        self.assignment_dialog_open = False

    def set_assignment_dialog_open(self, open: bool):
        """Set assignment dialog open state"""
        self.assignment_dialog_open = open
        if not open:
            self.close_assignment_dialog()

    def set_assignment_project(self, project_id: str):
        """Set the project for assignment"""
        self.assignment_project_id = project_id

    def set_assignment_roles(self, roles: List[str]):
        """Set the roles for assignment"""
        self.assignment_roles = roles

    def toggle_assignment_role(self, role: str):
        """Toggle a role in the assignment"""
        if role in self.assignment_roles:
            self.assignment_roles = [r for r in self.assignment_roles if r != role]
        else:
            self.assignment_roles = self.assignment_roles + [role]

    async def assign_user_to_project_from_dialog(self):
        """Assign user to project using dialog data"""
        async def assign_user_from_dialog():
            if not self.assignment_user_id or not self.assignment_project_id:
                self.error = "User and project are required"
                return False
                
            if not self.assignment_roles:
                self.error = "At least one role is required"
                return False
            
            org_id = await self.get_admin_organization_id()
            if not org_id:
                self.error = "Access denied: Admin privileges required"
                return False
            
            result = await UserManagementService.assign_user_to_project(
                self.assignment_user_id, 
                self.assignment_project_id, 
                self.assignment_roles, 
                org_id
            )
            
            if result.get("success"):
                self.close_assignment_dialog()
                await self.load_organization_users()  # Refresh user list
                return True
            else:
                self.error = result.get("error", "Failed to assign user to project")
                return False
        
        await self.handle_async_operation(
            assign_user_from_dialog,
            "User successfully assigned to project"
        )

    def get_user_project_assignments(self, user_id: str) -> List[Dict]:
        """Get project assignments for a specific user"""
        for user in self.organization_users:
            if user["id"] == user_id:
                return user.get("project_assignments", [])
        return []

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user data by ID"""
        for user in self.organization_users:
            if user["id"] == user_id:
                return user
        return None

    @rx.var
    def assignment_user_name(self) -> str:
        """Get the name of the user being assigned"""
        user = self.get_user_by_id(self.assignment_user_id)
        return user["username"] if user else ""

    @rx.var
    def assignment_project_name(self) -> str:
        """Get the name of the project being assigned"""
        for project in self.available_projects:
            if project["id"] == self.assignment_project_id:
                return project["name"]
        return ""

    @rx.var
    def available_project_options(self) -> List[str]:
        """Get list of available project names for dropdown"""
        return [project["name"] for project in self.available_projects]

    def get_project_id_by_name(self, project_name: str) -> str:
        """Get project ID by name"""
        for project in self.available_projects:
            if project["name"] == project_name:
                return project["id"]
        return ""

    def set_assignment_project_by_name(self, project_name: str):
        """Set assignment project by name"""
        self.assignment_project_id = self.get_project_id_by_name(project_name) 

    def open_project_management_dialog(self, user_id: str):
        """Open project management dialog for a specific user"""
        self.project_management_user_id = user_id
        self.project_management_dialog_open = True

    def close_project_management_dialog(self):
        """Close project management dialog"""
        self.project_management_user_id = ""
        self.project_management_dialog_open = False

    def set_project_management_dialog_open(self, open: bool):
        """Set project management dialog open state"""
        self.project_management_dialog_open = open
        if not open:
            self.close_project_management_dialog()

    @rx.var
    def project_management_user_name(self) -> str:
        """Get the name of the user being managed"""
        user = self.get_user_by_id(self.project_management_user_id)
        return user["username"] if user else ""

    @rx.var
    def project_management_user_assignments(self) -> List[Dict]:
        """Get current project assignments for the user being managed"""
        user = self.get_user_by_id(self.project_management_user_id)
        return user.get("project_assignments", []) if user else []

 