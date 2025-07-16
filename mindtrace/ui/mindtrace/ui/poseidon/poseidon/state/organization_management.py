import reflex as rx
from poseidon.backend.services.organization_management_service import OrganizationManagementService
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.state.base import BaseDialogState, RoleBasedAccessMixin
from poseidon.state.models import OrganizationData, SubscriptionPlans, StatusTypes
from poseidon.state.auth import AuthState
from typing import List, Dict, Optional


class OrganizationManagementState(BaseDialogState, RoleBasedAccessMixin):
    """State management for organization administration operations."""
    
    # Organization Management Data
    organizations: List[OrganizationData] = []
    
    # Additional Filters (extends BaseFilterState)
    plan_filter: str = ""  # basic, premium, enterprise, all
    
    # Add Organization Form Data
    new_org_name: str = ""
    new_org_description: str = ""
    new_org_plan: str = SubscriptionPlans.BASIC
    new_org_max_users: str = "50"
    new_org_max_projects: str = "10"
    
    # Edit Organization Form Data
    edit_org_id: str = ""
    edit_org_name: str = ""
    edit_org_description: str = ""
    edit_org_plan: str = ""
    edit_org_max_users: str = "0"
    edit_org_max_projects: str = "0"

    async def load_organizations(self):
        """Load all organizations (super admin only)"""
        async def load_organizations_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.error = "Access denied: Super Admin privileges required"
                return False
            
            organizations = await OrganizationManagementService.get_all_organizations()
            self.organizations = [
                OrganizationData(
                    id=str(org.id),
                    name=org.name or "",
                    description=org.description or "",
                    subscription_plan=org.subscription_plan or SubscriptionPlans.BASIC,
                    max_users=org.max_users if org.max_users is not None else 50,
                    max_projects=org.max_projects if org.max_projects is not None else 10,
                    admin_key=org.admin_registration_key or "",
                    is_active=org.is_active if org.is_active is not None else True,
                    created_at=str(org.created_at) if org.created_at else "",
                    updated_at=str(org.updated_at) if org.updated_at else ""
                )
                for org in organizations
            ]
            return True
        
        await self.handle_async_operation(
            load_organizations_data,
            "Organizations loaded successfully"
        )

    @rx.var
    def filtered_organizations(self) -> List[OrganizationData]:
        """Get filtered list of organizations"""
        orgs = self.organizations
        
        # Apply search filter
        orgs = self.filter_by_search(orgs, ["name", "description"])
        
        # Filter by subscription plan
        if self.plan_filter and self.plan_filter != "all":
            orgs = [
                org for org in orgs
                if org.subscription_plan == self.plan_filter
            ]
        
        # Apply status filter
        orgs = self.filter_by_status(orgs)
        
        return orgs

    @rx.var
    def available_plans(self) -> List[str]:
        """Get list of available subscription plans"""
        return SubscriptionPlans.get_all()
    
    @rx.var
    def available_display_plans(self) -> List[str]:
        """Get list of available plans for display"""
        return [SubscriptionPlans.get_display_names()[plan] for plan in SubscriptionPlans.get_all()]

    def can_edit_organization(self, target_org_id: str) -> bool:
        """Check if current user can edit the target organization"""
        # Only super admins can edit organizations
        from poseidon.state.auth import AuthState
        return AuthState.is_super_admin
    
    def can_deactivate_organization(self, target_org_id: str) -> bool:
        """Check if current user can deactivate the target organization"""
        # Only super admins can deactivate organizations
        from poseidon.state.auth import AuthState
        return AuthState.is_super_admin

    def clear_new_org_form(self):
        """Clear the new organization form data"""
        self.new_org_name = ""
        self.new_org_description = ""
        self.new_org_plan = SubscriptionPlans.BASIC
        self.new_org_max_users = "50"
        self.new_org_max_projects = "10"

    async def add_organization(self):
        """Add a new organization"""
        async def create_organization():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.error = "Access denied: Super Admin privileges required"
                return False
            
            # Validate form data
            if not self.validate_required_field(self.new_org_name, "Organization name"):
                return False
            
            # Convert plan to unified format
            plan_mapping = SubscriptionPlans.get_display_names()
            # Reverse mapping for display names to internal values
            reverse_plan_mapping = {v: k for k, v in plan_mapping.items()}
            reverse_plan_mapping.update({k: k for k in SubscriptionPlans.get_all()})  # Direct mappings
            
            backend_plan = reverse_plan_mapping.get(self.new_org_plan, SubscriptionPlans.BASIC)
            
            # Call organization management service to add organization
            result = await OrganizationManagementService.create_organization(
                name=self.new_org_name.strip(),
                description=self.new_org_description.strip(),
                subscription_plan=backend_plan,
                max_users=int(self.new_org_max_users) if self.new_org_max_users.isdigit() else 50,
                max_projects=int(self.new_org_max_projects) if self.new_org_max_projects.isdigit() else 10
            )
            
            if result.get("success"):
                self.clear_new_org_form()
                await self.load_organizations()  # Refresh organization list
                return True
            else:
                self.error = result.get("error", "Failed to add organization")
                return False
        
        await self.handle_async_operation(
            create_organization,
            f"Organization '{self.new_org_name}' added successfully"
        )

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
        async def update_organization_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.error = "Access denied: Super Admin privileges required"
                return False
            
            # Validate form data
            if not self.validate_required_field(self.edit_org_name, "Organization name"):
                return False
            
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
                self.clear_edit_org_form()
                await self.load_organizations()  # Refresh organization list
                return True
            else:
                self.error = result.get("error", "Failed to update organization")
                return False
        
        await self.handle_async_operation(
            update_organization_data,
            f"Organization '{self.edit_org_name}' updated successfully"
        )

    async def deactivate_organization(self, org_id: str):
        """Deactivate an organization"""
        async def deactivate_organization_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.error = "Access denied: Super Admin privileges required"
                return False
            
            result = await OrganizationManagementService.deactivate_organization(org_id)
            
            if result.get("success"):
                await self.load_organizations()  # Refresh organization list
                return True
            return False
        
        await self.handle_async_operation(
            deactivate_organization_data,
            "Organization deactivated successfully"
        )

    async def activate_organization(self, org_id: str):
        """Activate an organization"""
        async def activate_organization_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.error = "Access denied: Super Admin privileges required"
                return False
            
            result = await OrganizationManagementService.activate_organization(org_id)
            
            if result.get("success"):
                await self.load_organizations()  # Refresh organization list
                return True
            return False
        
        await self.handle_async_operation(
            activate_organization_data,
            "Organization activated successfully"
        ) 