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
    
    # Edit Project Form Data
    edit_project_id: str = ""
    edit_project_name: str = ""
    edit_project_description: str = ""
    edit_project_organization_id: str = ""

    # Dialog Control
    add_project_dialog_open: bool = False

    async def open_add_project_dialog(self):
        """Open the add project dialog"""
        self.add_project_dialog_open = True
        await self.clear_new_project_form()

    async def close_add_project_dialog(self):
        """Close the add project dialog"""
        self.add_project_dialog_open = False
        await self.clear_new_project_form()

    async def set_add_project_dialog_open(self, open: bool):
        """Set add project dialog open state"""
        self.add_project_dialog_open = open
        if not open:
            await self.clear_new_project_form()

    async def load_organizations(self):
        """Load organizations for dropdown selection based on user role"""
        try:
            auth_state = await self.get_auth_state()
            if auth_state.is_super_admin:
                # Super admin can see all organizations
                orgs = await OrganizationRepository.get_all()
                self.organizations = [
                    {"id": str(org.id), "name": org.name}
                    for org in orgs
                ]
            elif auth_state.is_admin:
                # Regular admin can only see their organization
                if auth_state.user_organization_id:
                    org = await OrganizationRepository.get_by_id(auth_state.user_organization_id)
                    if org:
                        self.organizations = [{"id": str(org.id), "name": org.name}]
                        # Auto-set organization for regular admins
                        self.new_project_organization_id = str(org.id)
                        self.edit_project_organization_id = str(org.id)
        except Exception as e:
            self.error = f"Failed to load organizations: {str(e)}"

    async def load_projects(self):
        """Load projects based on user role"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_auth_state()
            
            if auth_state.is_super_admin:
                # Super admin sees all projects across all organizations
                projects = await ProjectRepository.get_all()
            elif auth_state.is_admin:
                # Regular admin sees only their organization's projects
                if auth_state.user_organization_id:
                    projects = await ProjectRepository.get_by_organization(auth_state.user_organization_id)
                else:
                    projects = []
            else:
                self.error = "Access denied: Admin privileges required"
                return
            
            # Convert to ProjectData objects
            self.projects = []
            for project in projects:
                # Get organization name and ID
                org_name = ""
                org_id = ""
                
                # Extract organization info from Link field
                if hasattr(project, 'organization') and project.organization:
                    org_id = str(project.organization.id)
                    org_name = project.organization.name if hasattr(project.organization, 'name') else "Unknown"
                else:
                    org_name = "Unknown"
                
                self.projects.append(ProjectData(
                    id=str(project.id),
                    name=project.name or "",
                    description=project.description or "",
                    organization_id=org_id,
                    organization_name=org_name,
                    status=project.status if hasattr(project, 'status') else ("active" if getattr(project, 'is_active', True) else "inactive"),
                    created_at=str(project.created_at) if project.created_at else "",
                    updated_at=str(project.updated_at) if project.updated_at else ""
                ))
            
            # Load organizations for form dropdowns
            await self.load_organizations()
            
        except Exception as e:
            self.error = f"Failed to load projects: {str(e)}"
        finally:
            self.loading = False

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
        
        # Apply status filter
        projects = self.filter_by_status(projects, "status")
        
        return projects

    @rx.var
    def organization_options(self) -> List[str]:
        """Get organization options for dropdown"""
        return [org["name"] for org in self.organizations]

    @rx.var
    def organization_filter_options(self) -> List[str]:
        """Get organization filter options including 'all'"""
        return ["all"] + [org["name"] for org in self.organizations]

    @rx.var
    def show_organization_selector(self) -> bool:
        """Show organization selector only for super admins"""
        return len(self.organizations) > 1

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

    async def add_project(self):
        """Add a new project"""
        async def create_project():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.error = "Access denied: Admin privileges required"
                return False
            
            # Validate form data
            if not self.validate_required_field(self.new_project_name, "Project name"):
                return False
            
            # For regular admins, auto-set organization if not set
            if auth_state.is_admin and not auth_state.is_super_admin:
                if not self.new_project_organization_id and auth_state.user_organization_id:
                    self.new_project_organization_id = auth_state.user_organization_id
            
            if not self.validate_required_field(self.new_project_organization_id, "Organization"):
                return False
            
            # Create project
            project = await ProjectRepository.create({
                "name": self.new_project_name.strip(),
                "description": self.new_project_description.strip(),
                "organization_id": self.new_project_organization_id,
                "status": "active"
            })
            
            if project:
                await self.close_add_project_dialog()
                await self.load_projects()  # Refresh project list
                return True
            return False
        
        await self.handle_async_operation(
            create_project,
            f"Project '{self.new_project_name}' created successfully"
        )

    def set_edit_project_data(self, project_data: ProjectData):
        """Set edit project form data from selected project"""
        self.edit_project_id = project_data.id
        self.edit_project_name = project_data.name
        self.edit_project_description = project_data.description
        self.edit_project_organization_id = project_data.organization_id

    def clear_edit_project_form(self):
        """Clear the edit project form data"""
        self.edit_project_id = ""
        self.edit_project_name = ""
        self.edit_project_description = ""
        self.edit_project_organization_id = ""

    def handle_edit_dialog_change(self, open: bool):
        """Handle edit dialog open/close state changes"""
        if not open:
            self.clear_edit_project_form()

    async def update_project(self):
        """Update an existing project"""
        async def update_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.error = "Access denied: Admin privileges required"
                return False
            
            # Validate form data
            if not self.validate_required_field(self.edit_project_name, "Project name"):
                return False
            
            # Update project
            project = await ProjectRepository.update(self.edit_project_id, {
                "name": self.edit_project_name.strip(),
                "description": self.edit_project_description.strip(),
                "organization_id": self.edit_project_organization_id
            })
            
            if project:
                self.clear_edit_project_form()
                await self.load_projects()  # Refresh project list
                return True
            return False
        
        await self.handle_async_operation(
            update_project_data,
            f"Project '{self.edit_project_name}' updated successfully"
        )

    async def deactivate_project(self, project_id: str):
        """Deactivate a project"""
        async def deactivate_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.error = "Access denied: Admin privileges required"
                return False
            
            project = await ProjectRepository.update(project_id, {"status": "inactive"})
            
            if project:
                await self.load_projects()  # Refresh project list
                return True
            return False
        
        await self.handle_async_operation(
            deactivate_project_data,
            "Project deactivated successfully"
        )

    async def activate_project(self, project_id: str):
        """Activate a project"""
        async def activate_project_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_projects(auth_state.is_admin, auth_state.is_super_admin):
                self.error = "Access denied: Admin privileges required"
                return False
            
            project = await ProjectRepository.update(project_id, {"status": "active"})
            
            if project:
                await self.load_projects()  # Refresh project list
                return True
            return False
        
        await self.handle_async_operation(
            activate_project_data,
            "Project activated successfully"
        )

    @rx.var
    def new_project_organization_name(self) -> str:
        """Get organization name for new project"""
        for org in self.organizations:
            if org["id"] == self.new_project_organization_id:
                return org["name"]
        return ""

    @rx.var
    def edit_project_organization_name(self) -> str:
        """Get organization name for edit project"""
        for org in self.organizations:
            if org["id"] == self.edit_project_organization_id:
                return org["name"]
        return ""

    def get_organization_name_by_id(self, org_id: str) -> str:
        """Get organization name by ID"""
        for org in self.organizations:
            if org["id"] == org_id:
                return org["name"]
        return "Unknown"

    def get_organization_id_by_name(self, org_name: str) -> str:
        """Get organization ID by name"""
        for org in self.organizations:
            if org["name"] == org_name:
                return org["id"]
        return ""

    def set_new_project_organization_by_name(self, org_name: str):
        """Set new project organization by name"""
        self.new_project_organization_id = self.get_organization_id_by_name(org_name)

    def set_edit_project_organization_by_name(self, org_name: str):
        """Set edit project organization by name"""
        self.edit_project_organization_id = self.get_organization_id_by_name(org_name) 