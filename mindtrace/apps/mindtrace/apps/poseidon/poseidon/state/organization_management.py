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
    add_org_dialog_open: bool = False
    
    # Edit Organization Form Data
    edit_org_id: str = ""
    edit_org_name: str = ""
    edit_org_description: str = ""
    edit_org_plan: str = ""
    edit_org_max_users: str = "0"
    edit_org_max_projects: str = "0"
    edit_org_dialog_open: bool = False

    # --- Computed Properties ---
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

    # --- Dialog Management ---
    def open_add_org_dialog(self):
        """Open add organization dialog"""
        self.open_dialog("add_org")
        self.clear_new_org_form()

    def close_add_org_dialog(self):
        """Close add organization dialog"""
        self.close_dialog("add_org")
        self.clear_new_org_form()

    def open_edit_org_dialog(self, org_data: OrganizationData):
        """Open edit organization dialog with data"""
        self.edit_org_id = org_data.id
        self.edit_org_name = org_data.name
        self.edit_org_description = org_data.description
        self.edit_org_plan = org_data.subscription_plan
        self.edit_org_max_users = str(org_data.max_users)
        self.edit_org_max_projects = str(org_data.max_projects)
        self.open_dialog("edit_org")

    def close_edit_org_dialog(self):
        """Close edit organization dialog"""
        self.close_dialog("edit_org")
        self.clear_edit_org_form()

    def set_edit_org_data(self, org_data):
        """Set edit organization data from organization object"""
        self.edit_org_id = str(org_data.id)
        self.edit_org_name = org_data.name
        self.edit_org_description = org_data.description or ""
        self.edit_org_plan = org_data.subscription_plan
        self.edit_org_max_users = str(org_data.max_users or 50)
        self.edit_org_max_projects = str(org_data.max_projects or 10)

    # --- Data Loading ---
    async def load_organizations(self):
        """Load organizations (super admin only)"""
        async def load_org_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.set_error("Access denied: Super Admin privileges required")
                return False
            
            orgs = await OrganizationRepository.get_all()
            
            self.organizations = [
                OrganizationData(
                    id=str(org.id),
                    name=org.name,
                    description=org.description or "",
                    subscription_plan=org.subscription_plan,
                    max_users=org.max_users,
                    max_projects=org.max_projects,
                    admin_key=org.admin_registration_key,
                    is_active=org.is_active,
                    created_at=org.created_at,
                    updated_at=org.updated_at
                )
                for org in orgs
            ]
            return True

        await self.handle_async_operation(load_org_data, "Organizations loaded successfully")

    # --- Form Management ---
    def clear_new_org_form(self):
        """Clear the new organization form data"""
        self.new_org_name = ""
        self.new_org_description = ""
        self.new_org_plan = SubscriptionPlans.BASIC
        self.new_org_max_users = "50"
        self.new_org_max_projects = "10"

    def clear_edit_org_form(self):
        """Clear the edit organization form data"""
        self.edit_org_id = ""
        self.edit_org_name = ""
        self.edit_org_description = ""
        self.edit_org_plan = ""
        self.edit_org_max_users = "0"
        self.edit_org_max_projects = "0"

    # --- CRUD Operations ---
    async def add_organization(self):
        """Add a new organization"""
        async def create_organization():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.set_error("Access denied: Super Admin privileges required")
                return False
            
            # Validate form data
            if not self.validate_required_field(self.new_org_name, "Organization name"):
                return False
            
            if not self.validate_positive_integer(self.new_org_max_users, "Max users"):
                return False
                
            if not self.validate_positive_integer(self.new_org_max_projects, "Max projects"):
                return False
            
            # Convert plan to unified format
            plan_mapping = SubscriptionPlans.get_display_names()
            reverse_plan_mapping = {v: k for k, v in plan_mapping.items()}
            reverse_plan_mapping.update({k: k for k in SubscriptionPlans.get_all()})
            
            backend_plan = reverse_plan_mapping.get(self.new_org_plan, SubscriptionPlans.BASIC)
            
            # Call organization management service to add organization
            result = await OrganizationManagementService.create_organization(
                name=self.new_org_name.strip(),
                description=self.new_org_description.strip(),
                subscription_plan=backend_plan,
                max_users=int(self.new_org_max_users),
                max_projects=int(self.new_org_max_projects)
            )
            
            if result.get("success"):
                self.close_add_org_dialog()
                await self.load_organizations()
                return True
            else:
                self.set_error(result.get("error", "Failed to add organization"))
                return False
        
        await self.handle_async_operation(
            create_organization,
            f"Organization '{self.new_org_name}' added successfully"
        )

    async def update_organization(self):
        """Update an existing organization"""
        async def update_org_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.set_error("Access denied: Super Admin privileges required")
                return False
            
            # Validate form data
            if not self.validate_required_field(self.edit_org_name, "Organization name"):
                return False
            
            if not self.validate_positive_integer(self.edit_org_max_users, "Max users"):
                return False
                
            if not self.validate_positive_integer(self.edit_org_max_projects, "Max projects"):
                return False
            
            # Convert plan to unified format
            plan_mapping = SubscriptionPlans.get_display_names()
            reverse_plan_mapping = {v: k for k, v in plan_mapping.items()}
            reverse_plan_mapping.update({k: k for k in SubscriptionPlans.get_all()})
            
            backend_plan = reverse_plan_mapping.get(self.edit_org_plan, SubscriptionPlans.BASIC)
            
            # Update organization
            result = await OrganizationManagementService.update_organization(
                org_id=self.edit_org_id,
                name=self.edit_org_name.strip(),
                description=self.edit_org_description.strip(),
                subscription_plan=backend_plan,
                max_users=int(self.edit_org_max_users),
                max_projects=int(self.edit_org_max_projects)
            )
            
            if result.get("success"):
                self.close_edit_org_dialog()
                await self.load_organizations()
                return True
            else:
                self.set_error(result.get("error", "Failed to update organization"))
                return False
        
        await self.handle_async_operation(
            update_org_data,
            f"Organization '{self.edit_org_name}' updated successfully"
        )

    async def delete_organization(self, org_id: str):
        """Delete an organization"""
        async def delete_org_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.set_error("Access denied: Super Admin privileges required")
                return False
            
            result = await OrganizationManagementService.delete_organization(org_id)
            
            if result.get("success"):
                await self.load_organizations()
                return True
            else:
                self.set_error(result.get("error", "Failed to delete organization"))
            return False
        
        await self.handle_async_operation(
            delete_org_data,
            "Organization deleted successfully"
        )

    async def activate_organization(self, org_id: str):
        """Activate an organization"""
        async def activate_org_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.set_error("Access denied: Super Admin privileges required")
                return False
            
            result = await OrganizationManagementService.activate_organization(org_id)
            
            if result.get("success"):
                await self.load_organizations()
                return True
            else:
                self.set_error(result.get("error", "Failed to activate organization"))
            return False
        
        await self.handle_async_operation(
            activate_org_data,
            "Organization activated successfully"
        ) 

    async def deactivate_organization(self, org_id: str):
        """Deactivate an organization"""
        async def deactivate_org_data():
            auth_state = await self.get_auth_state()
            if not self.can_manage_organization(auth_state.is_super_admin):
                self.set_error("Access denied: Super Admin privileges required")
                return False
            
            result = await OrganizationManagementService.deactivate_organization(org_id)
            
            if result.get("success"):
                await self.load_organizations()
                return True
            else:
                self.set_error(result.get("error", "Failed to deactivate organization"))
                return False

        await self.handle_async_operation(
            deactivate_org_data,
            "Organization deactivated successfully"
        )

    # --- Filter Management ---
    def set_plan_filter(self, plan: str):
        """Set subscription plan filter"""
        self.plan_filter = plan

    def clear_plan_filter(self):
        """Clear subscription plan filter"""
        self.plan_filter = ""

    # --- Utility Methods ---
    def can_edit_organization(self, target_org_id: str) -> bool:
        """Check if current user can edit the target organization"""
        # Only super admins can edit organizations
        return True  # Will be checked in async operations

    def can_deactivate_organization(self, target_org_id: str) -> bool:
        """Check if current user can deactivate the target organization"""
        # Only super admins can deactivate organizations
        return True  # Will be checked in async operations 