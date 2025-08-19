import reflex as rx
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.state.base import BaseDialogState, RoleBasedAccessMixin
from poseidon.state.models import ProjectData, OrganizationData, StatusTypes
from poseidon.state.auth import AuthState
from typing import List, Dict, Optional


class ProjectManagementState(BaseDialogState, RoleBasedAccessMixin):
    """State management for project administration operations."""
    
    # Project Management Data
    projects: List[ProjectData] = []
    organizations: List[Dict] = []  # For dropdown selection
    
    # Additional Filters (extends BaseFilterState)
    organization_filter: str = ""  # Filter by organization
    
    # Add Project Form Data
    new_project_name: str = ""
    new_project_description: str = ""
    new_project_organization_id: str = ""
    add_project_dialog_open: bool = False
    
    # Edit Project Form Data
    edit_project_id: str = ""
    edit_project_name: str = ""
    edit_project_description: str = ""
    edit_project_organization_id: str = ""
    edit_project_dialog_open: bool = False

    # --- Computed Properties ---
    @rx.var
    def filtered_projects(self) -> List[ProjectData]:
        """Get filtered list of projects"""
        projects = self.projects
        
        # Apply search filter
        projects = self.filter_by_search(projects, ["name", "description"])
        
        # Filter by organization
        if self.organization_filter and self.organization_filter != "all":
            projects = [
                project for project in projects
                if project.organization_id == self.organization_filter
            ]
        
        # Apply status filter (projects use 'status' field with string values)
        if self.status_filter == "active":
            projects = [p for p in projects if p.status == "active"]
        elif self.status_filter == "inactive":
            projects = [p for p in projects if p.status == "inactive"]
        # "all" shows all projects
        
        return projects

    @rx.var
    def show_organization_selector(self) -> bool:
        """Check if organization selector should be shown"""
        return len(self.organizations) > 0
    
    @rx.var
    def organization_options(self) -> List[str]:
        """Get list of organization names for dropdown"""
        return [org.get("name", "") for org in self.organizations]
    
    @rx.var
    def new_project_organization_name(self) -> str:
        """Get organization name for new project based on selected organization ID"""
        for org in self.organizations:
            if org.get("id") == self.new_project_organization_id:
                return org.get("name", "")
        return ""
    
    @rx.var
    def edit_project_organization_name(self) -> str:
        """Get organization name for edit project based on selected organization ID"""
        for org in self.organizations:
            if org.get("id") == self.edit_project_organization_id:
                return org.get("name", "")
        return ""

    # --- Dialog Management ---
    async def open_add_project_dialog(self):
        """Open the add project dialog"""
        self.add_project_dialog_open = True
        self.clear_messages()
        await self.clear_new_project_form()
        await self.load_organizations()

    async def close_add_project_dialog(self):
        """Close the add project dialog"""
        self.add_project_dialog_open = False
        self.clear_messages()
        await self.clear_new_project_form()

    def open_edit_project_dialog(self, project_data: ProjectData):
        """Open edit project dialog with data"""
        self.edit_project_id = project_data.id
        self.edit_project_name = project_data.name
        self.edit_project_description = project_data.description
        self.edit_project_organization_id = project_data.organization_id
        self.edit_project_dialog_open = True
        self.clear_messages()

    def close_edit_project_dialog(self):
        """Close edit project dialog"""
        self.edit_project_dialog_open = False
        self.clear_messages()
        self.clear_edit_project_form()

    def set_edit_project_data(self, project_data: ProjectData):
        """Set edit project data from project object"""
        self.edit_project_id = project_data.id
        self.edit_project_name = project_data.name
        self.edit_project_description = project_data.description or ""
        self.edit_project_organization_id = project_data.organization_id

    def set_new_project_organization_by_name(self, organization_name: str):
        """Set new project organization ID based on organization name"""
        for org in self.organizations:
            if org.get("name") == organization_name:
                self.new_project_organization_id = org.get("id", "")
                break

    def set_edit_project_organization_by_name(self, organization_name: str):
        """Set edit project organization ID based on organization name"""
        for org in self.organizations:
            if org.get("name") == organization_name:
                self.edit_project_organization_id = org.get("id", "")
                break

    def handle_edit_dialog_change(self, open: bool):
        """Handle edit dialog open/close state changes"""
        self.edit_project_dialog_open = open
        if not open:
            self.clear_edit_project_form()

    # --- Data Loading Methods ---
    async def load_organizations(self):
        """Load organizations for dropdown selection based on user role"""
        async def load_orgs():
            auth_state = await self.get_auth_state()
            
            if auth_state.is_super_admin:
                # Super admin can see all organizations
                orgs = await OrganizationRepository.get_all()
                self.organizations = [
                    {"id": str(org.id), "name": org.name}
                    for org in orgs
                ]
                # Don't auto-set organization for super admins - let them choose
            elif auth_state.is_admin:
                # Regular admin can only see their organization
                if auth_state.user_organization_id:
                    org = await OrganizationRepository.get_by_id(auth_state.user_organization_id)
                    if org:
                        self.organizations = [{"id": str(org.id), "name": org.name}]
                        # Auto-set organization for regular admins
                        self.new_project_organization_id = str(org.id)
                        self.edit_project_organization_id = str(org.id)
                    else:
                        self.set_error("Organization not found")
                        return False
                else:
                    self.set_error("No organization assigned to admin user")
                    return False
            else:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            return True

        await self.handle_async_operation(load_orgs, "Organizations loaded successfully")

    async def load_projects(self):
        """Load projects based on user role"""
        async def load_project_data():
            auth_state = await self.get_auth_state()
            
            # Clear existing projects to ensure fresh data
            self.projects = []
            
            if auth_state.is_super_admin:
                # Super admin sees all projects across all organizations
                projects = await ProjectRepository.get_all()
            elif auth_state.is_admin:
                # Regular admin sees only their organization's projects
                if auth_state.user_organization_id:
                    projects = await ProjectRepository.get_by_organization(auth_state.user_organization_id)
                else:
                    self.set_error("No organization assigned to admin")
                    return False
            else:
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # Convert to ProjectData objects
            for project in projects:
                # Fetch organization link if needed
                if hasattr(project, 'organization') and project.organization:
                    if not hasattr(project.organization, 'name'):
                        await project.fetch_link("organization")
                    
                    project_data = ProjectData(
                    id=str(project.id),
                        name=project.name,
                    description=project.description or "",
                        organization_id=str(project.organization.id),
                        organization_name=project.organization.name,
                        status=project.status,
                        created_at=project.created_at,
                        updated_at=project.updated_at
                    )
                    self.projects.append(project_data)
            
            return True

        await self.handle_async_operation(load_project_data, "Projects loaded successfully")

    # --- Form Management ---
    async def clear_new_project_form(self):
        """Clear the new project form data"""
        self.new_project_name = ""
        self.new_project_description = ""
        
        # Don't clear organization_id for regular admins as it's auto-set
        try:
            auth_state = await self.get_auth_state()
            if not auth_state or not auth_state.is_admin or auth_state.is_super_admin:
                self.new_project_organization_id = ""
        except:
            # If we can't get auth state, clear the organization_id
            self.new_project_organization_id = ""

    def clear_edit_project_form(self):
        """Clear the edit project form data"""
        self.edit_project_id = ""
        self.edit_project_name = ""
        self.edit_project_description = ""
        self.edit_project_organization_id = ""

    # --- CRUD Operations ---
    async def add_project(self):
        """Add a new project"""
        async def create_project():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # Validate form data
            if not self.validate_required_field(self.new_project_name, "Project name"):
                return False
            
            # For regular admins, auto-set organization if not set
            if auth_state.is_admin and not auth_state.is_super_admin:
                if not self.new_project_organization_id and auth_state.user_organization_id:
                    self.new_project_organization_id = auth_state.user_organization_id
            
            # Validate organization selection
            if not self.validate_required_field(self.new_project_organization_id, "Organization"):
                if auth_state.is_super_admin:
                    self.set_error("Super admins must select an organization for the project")
                else:
                    self.set_error("Organization is required")
                return False
            
            # Create project
            project = await ProjectRepository.create({
                "name": self.new_project_name.strip(),
                "description": self.new_project_description.strip(),
                "organization_id": self.new_project_organization_id,
                "owner_id": auth_state.user_id,
                "status": "active"
            })
            
            if project:
                await self.close_add_project_dialog()
                await self.load_projects()
                return True
            else:
                self.set_error("Failed to create project")
            return False
        
        await self.handle_async_operation(
            create_project,
            f"Project '{self.new_project_name}' created successfully"
        )

    async def update_project(self):
        """Update an existing project"""
        async def update_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # Validate form data
            if not self.validate_required_field(self.edit_project_name, "Project name"):
                return False
            
            if not self.validate_required_field(self.edit_project_organization_id, "Organization"):
                return False
            
            # Get current project to validate organization changes
            current_project = await ProjectRepository.get_by_id(self.edit_project_id)
            if not current_project:
                self.set_error("Project not found")
                return False
            
            # SECURITY: Prevent cross-organization project moves (unless super admin)
            current_org_id = str(current_project.organization.id)
            new_org_id = self.edit_project_organization_id
            
            if current_org_id != new_org_id and not auth_state.is_super_admin:
                self.set_error("Access denied: Cannot move projects between organizations")
                return False
            
            # For regular admins, ensure both orgs are theirs
            if auth_state.is_admin and not auth_state.is_super_admin:
                if (current_org_id != auth_state.user_organization_id or 
                    new_org_id != auth_state.user_organization_id):
                    self.set_error("Access denied: Project and organization must be yours")
                    return False
            
            # Update project
            success = await ProjectRepository.update(self.edit_project_id, {
                "name": self.edit_project_name.strip(),
                "description": self.edit_project_description.strip(),
                "organization_id": self.edit_project_organization_id
            })
            
            if success:
                self.close_edit_project_dialog()
                await self.load_projects()
                return True
            else:
                self.set_error("Failed to update project")
            return False
        
        await self.handle_async_operation(
            update_project_data,
            f"Project '{self.edit_project_name}' updated successfully"
        )

    async def delete_project(self, project_id: str):
        """Delete a project"""
        async def delete_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.set_error("Access denied: Admin privileges required")
                return False
            
            success = await ProjectRepository.delete(project_id)
            
            if success:
                await self.load_projects()
                return True
            else:
                self.set_error("Failed to delete project")
            return False
        
        await self.handle_async_operation(
            delete_project_data,
            "Project deleted successfully"
        )

    async def activate_project(self, project_id: str):
        """Activate a project (admin/super admin only)"""
        async def activate_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # For regular admins, validate organization access
            if auth_state.is_admin and not auth_state.is_super_admin:
                project = await ProjectRepository.get_by_id(project_id)
                if not project or str(project.organization.id) != auth_state.user_organization_id:
                    self.set_error("Access denied: Project not in your organization")
                    return False
            
            success = await ProjectRepository.update(project_id, {"status": "active"})
            
            if success:
                await self.load_projects()
                return True
            else:
                self.set_error("Failed to activate project")
            return False
        
        await self.handle_async_operation(
            activate_project_data,
            "Project activated successfully"
        )

    async def deactivate_project(self, project_id: str):
        """Deactivate a project (admin/super admin only)"""
        async def deactivate_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.set_error("Access denied: Admin privileges required")
                return False
            
            # For regular admins, validate organization access
            if auth_state.is_admin and not auth_state.is_super_admin:
                project = await ProjectRepository.get_by_id(project_id)
                if not project or str(project.organization.id) != auth_state.user_organization_id:
                    self.set_error("Access denied: Project not in your organization")
                    return False
            
            success = await ProjectRepository.update(project_id, {"status": "inactive"})
            
            if success:
                await self.load_projects()
                return True
            else:
                self.set_error("Failed to deactivate project")
                return False

        await self.handle_async_operation(
            deactivate_project_data,
            "Project deactivated successfully"
        )

    async def delete_project(self, project_id: str):
        """Delete a project"""
        async def delete_project_data():
            auth_state = await self.get_auth_state()
            
            # Get organization ID for security check
            if auth_state.is_super_admin:
                # Super admin can delete any project
                success = await ProjectRepository.delete(project_id)
            else:
                # Regular admin can only delete projects in their organization
                success = await ProjectRepository.delete(project_id, auth_state.user_organization_id)
            
            if success:
                await self.load_projects()
                return True
            else:
                self.set_error("Failed to delete project")
                return False

        await self.handle_async_operation(
            delete_project_data,
            "Project deleted successfully"
        )

    # --- Filter Management ---
    def set_organization_filter(self, organization_id: str):
        """Set organization filter"""
        self.organization_filter = organization_id

    def clear_organization_filter(self):
        """Clear organization filter"""
        self.organization_filter = "" 