import reflex as rx
from poseidon.backend.services.organization_management_service import OrganizationManagementService
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.state.auth import AuthState
from typing import List, Dict, Optional


class OrganizationData(rx.Base):
    """Organization data model for frontend"""
    id: str
    name: str
    description: str = ""
    subscription_plan: str = "basic"
    max_users: Optional[int] = 50
    max_projects: Optional[int] = 10
    admin_key: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class OrganizationManagementState(rx.State):
    """State management for organization administration operations."""
    
    # UI State
    error: str = ""
    success: str = ""
    loading: bool = False
    
    # Organization Management Data
    organizations: List[OrganizationData] = []
    
    # Filters and Search
    search_query: str = ""
    status_filter: str = "active"  # active, inactive, all
    plan_filter: str = ""  # basic, premium, enterprise, all
    
    # Add Organization Form Data
    new_org_name: str = ""
    new_org_description: str = ""
    new_org_plan: str = "basic"
    new_org_max_users: str = "50"
    new_org_max_projects: str = "10"
    
    # Edit Organization Form Data
    edit_org_id: str = ""
    edit_org_name: str = ""
    edit_org_description: str = ""
    edit_org_plan: str = ""
    edit_org_max_users: str = "0"
    edit_org_max_projects: str = "0"

    def clear_messages(self):
        """Clear success and error messages"""
        self.error = ""
        self.success = ""

    async def load_organizations(self):
        """Load all organizations (super admin only)"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_super_admin:
                self.error = "Access denied: Super Admin privileges required"
                return
            
            organizations = await OrganizationManagementService.get_all_organizations()
            self.organizations = [
                OrganizationData(
                    id=str(org.id),
                    name=org.name or "",
                    description=org.description or "",
                    subscription_plan=org.subscription_plan or "basic",
                    max_users=org.max_users if org.max_users is not None else 50,
                    max_projects=org.max_projects if org.max_projects is not None else 10,
                    admin_key=org.admin_registration_key or "",
                    is_active=org.is_active if org.is_active is not None else True,
                    created_at=str(org.created_at) if org.created_at else "",
                    updated_at=str(org.updated_at) if org.updated_at else ""
                )
                for org in organizations
            ]
            
        except Exception as e:
            self.error = f"Failed to load organizations: {str(e)}"
        finally:
            self.loading = False

    @rx.var
    def filtered_organizations(self) -> List[OrganizationData]:
        """Get filtered list of organizations"""
        orgs = self.organizations
        
        # Filter by search query
        if self.search_query:
            orgs = [
                org for org in orgs
                if (self.search_query.lower() in org.name.lower() or
                    self.search_query.lower() in org.description.lower())
            ]
        
        # Filter by subscription plan
        if self.plan_filter and self.plan_filter != "all":
            orgs = [
                org for org in orgs
                if org.subscription_plan == self.plan_filter
            ]
        
        # Filter by status
        if self.status_filter == "active":
            orgs = [org for org in orgs if org.is_active]
        elif self.status_filter == "inactive":
            orgs = [org for org in orgs if not org.is_active]
        # "all" shows all organizations
        
        return orgs

    @rx.var
    def available_plans(self) -> List[str]:
        """Get list of available subscription plans"""
        return ["basic", "premium", "enterprise"]
    
    @rx.var
    def available_display_plans(self) -> List[str]:
        """Get list of available plans for display"""
        return ["Basic", "Premium", "Enterprise"]

    def can_edit_organization(self, target_org_id: str) -> bool:
        """Check if current user can edit the target organization"""
        # Only super admins can edit organizations
        return AuthState.is_super_admin
    
    def can_deactivate_organization(self, target_org_id: str) -> bool:
        """Check if current user can deactivate the target organization"""
        # Only super admins can deactivate organizations
        return AuthState.is_super_admin

    def clear_new_org_form(self):
        """Clear the new organization form data"""
        self.new_org_name = ""
        self.new_org_description = ""
        self.new_org_plan = "basic"
        self.new_org_max_users = "50"
        self.new_org_max_projects = "10"

    async def add_organization(self):
        """Add a new organization"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_super_admin:
                self.error = "Access denied: Super Admin privileges required"
                return
            
            # Validate form data
            if not self.new_org_name.strip():
                self.error = "Organization name is required"
                return
            
            # Convert plan to unified format
            plan_mapping = {
                "Basic": "basic",
                "Premium": "premium",
                "Enterprise": "enterprise",
                # Direct plan names (no conversion needed)
                "basic": "basic",
                "premium": "premium",
                "enterprise": "enterprise"
            }
            
            backend_plan = plan_mapping.get(self.new_org_plan, "basic")
            
            # Call organization management service to add organization
            result = await OrganizationManagementService.create_organization(
                name=self.new_org_name.strip(),
                description=self.new_org_description.strip(),
                subscription_plan=backend_plan,
                max_users=int(self.new_org_max_users) if self.new_org_max_users.isdigit() else 50,
                max_projects=int(self.new_org_max_projects) if self.new_org_max_projects.isdigit() else 10
            )
            
            if result.get("success"):
                self.success = f"Organization '{self.new_org_name}' added successfully"
                self.clear_new_org_form()
                await self.load_organizations()  # Refresh organization list
            else:
                self.error = result.get("error", "Failed to add organization")
            
        except Exception as e:
            self.error = f"Failed to add organization: {str(e)}"
        finally:
            self.loading = False

    def set_edit_org_data(self, org_data: OrganizationData):
        """Set edit organization form data from selected organization"""
        self.edit_org_id = org_data.id
        self.edit_org_name = org_data.name
        self.edit_org_description = org_data.description
        self.edit_org_plan = org_data.subscription_plan
        self.edit_org_max_users = str(org_data.max_users or 50)
        self.edit_org_max_projects = str(org_data.max_projects or 10)

    def clear_edit_org_form(self):
        """Clear the edit organization form data"""
        self.edit_org_id = ""
        self.edit_org_name = ""
        self.edit_org_description = ""
        self.edit_org_plan = ""
        self.edit_org_max_users = "0"
        self.edit_org_max_projects = "0"

    async def update_organization(self):
        """Update an existing organization"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_super_admin:
                self.error = "Access denied: Super Admin privileges required"
                return
            
            # Validate form data
            if not self.edit_org_name.strip():
                self.error = "Organization name is required"
                return
            
            # Update organization
            result = await OrganizationManagementService.update_organization(
                self.edit_org_id,
                {
                    "name": self.edit_org_name.strip(),
                    "description": self.edit_org_description.strip(),
                    "subscription_plan": self.edit_org_plan,
                    "max_users": int(self.edit_org_max_users) if self.edit_org_max_users.isdigit() else 50,
                    "max_projects": int(self.edit_org_max_projects) if self.edit_org_max_projects.isdigit() else 10
                }
            )
            
            if result.get("success"):
                self.success = f"Organization '{self.edit_org_name}' updated successfully"
                self.clear_edit_org_form()
                await self.load_organizations()  # Refresh organization list
            else:
                self.error = result.get("error", "Failed to update organization")
            
        except Exception as e:
            self.error = f"Failed to update organization: {str(e)}"
        finally:
            self.loading = False

    async def deactivate_organization(self, org_id: str):
        """Deactivate an organization"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_super_admin:
                self.error = "Access denied: Super Admin privileges required"
                return
            
            result = await OrganizationManagementService.deactivate_organization(org_id)
            
            if result.get("success"):
                self.success = "Organization deactivated successfully"
                await self.load_organizations()  # Refresh organization list
            
        except Exception as e:
            self.error = f"Failed to deactivate organization: {str(e)}"
        finally:
            self.loading = False

    async def activate_organization(self, org_id: str):
        """Activate an organization"""
        try:
            self.loading = True
            self.clear_messages()
            
            auth_state = await self.get_state(AuthState)
            if not auth_state.is_super_admin:
                self.error = "Access denied: Super Admin privileges required"
                return
            
            result = await OrganizationManagementService.activate_organization(org_id)
            
            if result.get("success"):
                self.success = "Organization activated successfully"
                await self.load_organizations()  # Refresh organization list
            
        except Exception as e:
            self.error = f"Failed to activate organization: {str(e)}"
        finally:
            self.loading = False 