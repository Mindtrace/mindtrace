"""License Management State

State management for license operations and UI.
Follows the established state patterns for consistency.
"""

import reflex as rx
from typing import List, Dict, Optional
from datetime import datetime, UTC, timedelta

from poseidon.backend.services.license_service import LicenseService
from poseidon.backend.database.models.enums import LicenseStatus, OrgRole
from poseidon.state.base import BasePaginationState, RoleBasedAccessMixin
from poseidon.state.auth import AuthState
from poseidon.state.models import LicenseData


class LicenseManagementState(BasePaginationState, RoleBasedAccessMixin):
    """License management state with role-based access control."""
    
    # License list and filtering
    organization_licenses: List[LicenseData] = []
    all_licenses: List[LicenseData] = []  # Super admin view
    filtered_licenses: List[LicenseData] = []
    license_status_filter: str = ""  # Renamed to avoid conflict with base class
    organization_filter: str = ""
    
    # Add license form
    add_license_dialog_open: bool = False
    add_license_project_id: str = ""
    add_license_project_name: str = ""
    add_license_expires_at: str = ""
    add_license_notes: str = ""
    
    # Renew license form
    renew_license_dialog_open: bool = False
    renew_license_id: str = ""
    renew_license_key: str = ""
    renew_license_project_name: str = ""
    renew_license_new_expires_at: str = ""
    
    # License details
    selected_license: LicenseData = LicenseData(id="", license_key="", status=LicenseStatus.ACTIVE)
    license_details_dialog_open: bool = False
    selected_license_id: str = ""  # For cancel operation
    
    # Available projects for licensing
    available_projects: List[Dict] = []
    
    # License statistics
    license_stats: Dict = {}
    expiring_licenses: List[LicenseData] = []
    
    # Organization filter options (super admin only)
    organization_filter_options: List[str] = []
    
    # --- Computed Properties ---
    @rx.var
    def total_pages(self) -> int:
        """Calculate total number of pages for filtered licenses"""
        return self.calculate_total_pages(self.filtered_licenses)
    
    @rx.var
    def paginated_licenses(self) -> List[LicenseData]:
        """Get licenses for current page"""
        return self.get_paginated_items(self.filtered_licenses)
    
    @rx.var
    def available_status_options(self) -> List[str]:
        """Get available license status options for filtering"""
        return ["all"] + [LicenseStatus.ACTIVE, LicenseStatus.EXPIRED, LicenseStatus.CANCELLED]
    
    @rx.var
    def available_project_options(self) -> List[str]:
        """Get available project names for licensing"""
        return [project.get("name", "") for project in self.available_projects]
    
    @rx.var
    def total_licenses_count(self) -> int:
        """Get total licenses count"""
        return len(self.organization_licenses if not self.is_super_admin_view else self.all_licenses)
    
    @rx.var
    def active_licenses_count(self) -> int:
        """Get active licenses count"""
        licenses = self.organization_licenses if not self.is_super_admin_view else self.all_licenses
        return len([lic for lic in licenses if lic.is_valid])
    
    # Cache for auth state to avoid async calls in computed properties
    _is_super_admin: bool = False
    
    @rx.var
    def is_super_admin_view(self) -> bool:
        """Check if current user can see super admin view"""
        return self._is_super_admin
    
    @rx.var
    def expiring_licenses_count(self) -> int:
        """Get count of expiring licenses"""
        return len(self.expiring_licenses)
    
    @rx.var
    def expiring_licenses_message(self) -> str:
        """Get message about expiring licenses"""
        count = len(self.expiring_licenses)
        if count == 0:
            return ""
        elif count == 1:
            return "1 license will expire within 30 days. Review and renew as needed."
        else:
            return f"{count} licenses will expire within 30 days. Review and renew as needed."
    
    @rx.var
    def organization_filter_items(self) -> List[Dict[str, str]]:
        """Get organization filter options formatted for select input"""
        return [{"id": org, "name": org} for org in self.organization_filter_options]
    
    # --- Data Loading Methods ---
    async def load_licenses(self):
        """Load licenses based on user role"""
        async def load_license_data():
            auth_state = await self.get_auth_state()
            self._is_super_admin = auth_state.is_super_admin  # Update cache
            
            if auth_state.is_super_admin:
                # Super admin sees all licenses
                result = await LicenseService.get_all_licenses(auth_state.user_id)
                if result.get("success"):
                    self.all_licenses = result.get("licenses", [])
                    self.filtered_licenses = self.all_licenses
                else:
                    self.set_error(result.get("error", "Failed to load licenses"))
                    return False
            else:
                # Regular admin sees only their organization's licenses
                result = await LicenseService.get_organization_licenses(
                    auth_state.user_organization_id,
                    auth_state.user_id
                )
                if result.get("success"):
                    self.organization_licenses = result.get("licenses", [])
                    self.filtered_licenses = self.organization_licenses
                else:
                    self.set_error(result.get("error", "Failed to load licenses"))
                    return False
            
            self.filter_licenses()
            return True

        await self.handle_async_operation(load_license_data, "Licenses loaded successfully")
    
    async def load_available_projects(self):
        """Load available projects for licensing"""
        async def load_projects():
            auth_state = await self.get_auth_state()
            
            from poseidon.backend.database.repositories.project_repository import ProjectRepository
            
            if auth_state.is_super_admin:
                # Super admin can license any project
                projects = await ProjectRepository.get_all()
            else:
                # Regular admin can only license projects in their organization
                projects = await ProjectRepository.get_by_organization(auth_state.user_organization_id)
            
            # Fetch organization links
            for project in projects:
                if not hasattr(project, '_organization_loaded'):
                    await project.fetch_link("organization")
                    project._organization_loaded = True
            
            # Only include active projects
            self.available_projects = [
                {
                    "id": str(project.id),
                    "name": project.name,
                    "organization_id": str(project.organization.id) if project.organization else "",
                    "organization_name": project.organization.name if project.organization else "Unknown"
                }
                for project in projects
                if project.status == "active"
            ]
            return True
            
        await self.handle_async_operation(load_projects, "Projects loaded successfully")
    
    async def load_license_stats(self):
        """Load license statistics"""
        async def load_stats():
            auth_state = await self.get_auth_state()
            
            # Get license stats
            stats_result = await LicenseService.get_license_stats(
                organization_id=None if auth_state.is_super_admin else auth_state.user_organization_id,
                admin_user_id=auth_state.user_id
            )
            
            if stats_result.get("success"):
                self.license_stats = stats_result.get("stats", {})
            else:
                self.license_stats = {}
            
            # Get expiring licenses
            expiring_result = await LicenseService.get_expiring_licenses(
                days=30,
                admin_user_id=auth_state.user_id
            )
            
            if expiring_result.get("success"):
                self.expiring_licenses = expiring_result.get("expiring_licenses", [])
            else:
                self.expiring_licenses = []
            
            return True
            
        await self.handle_async_operation(load_stats, "Statistics loaded successfully")
    
    async def load_organization_filter_options(self):
        """Load organization options for super admin filtering"""
        async def load_orgs():
            auth_state = await self.get_auth_state()
            
            if not auth_state.is_super_admin:
                return True  # No-op for non-super-admins
            
            from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
            
            organizations = await OrganizationRepository.get_all()
            self.organization_filter_options = ["all"] + [
                org.name for org in organizations
            ]
            return True
            
        await self.handle_async_operation(load_orgs, "Organization options loaded")
    
    # --- Filtering Methods ---
    def filter_licenses(self):
        """Filter licenses based on search query and filters"""
        if self.is_super_admin_view:
            filtered = self.all_licenses
        else:
            filtered = self.organization_licenses
        
        # Search filter
        if self.search_query:
            filtered = [
                lic for lic in filtered
                if (self.search_query.lower() in lic.license_key.lower() or
                    self.search_query.lower() in lic.project_name.lower() or
                    self.search_query.lower() in lic.organization_name.lower())
            ]
        
        # Status filter
        if self.license_status_filter and self.license_status_filter != "all":
            filtered = [
                lic for lic in filtered
                if lic.status == self.license_status_filter
            ]
        
        # Organization filter (super admin only)
        if self.organization_filter and self.organization_filter != "all" and self.is_super_admin_view:
            filtered = [
                lic for lic in filtered
                if lic.organization_name == self.organization_filter
            ]
        
        self.filtered_licenses = filtered
        # Reset to first page when filtering
        self.current_page = 1

    def set_search_query(self, query: str):
        """Set search query and filter licenses"""
        self.search_query = query
        self.filter_licenses()

    def set_license_status_filter(self, status: str):
        """Set status filter and filter licenses"""
        self.license_status_filter = status
        self.filter_licenses()

    def set_organization_filter(self, organization: str):
        """Set organization filter and filter licenses"""
        self.organization_filter = organization
        self.filter_licenses()

    def clear_filters(self):
        """Clear all filters"""
        super().clear_filters()
        self.license_status_filter = ""
        self.organization_filter = ""
        self.filter_licenses()

    # --- Dialog Management Methods ---
    async def open_add_license_dialog(self):
        """Open add license dialog"""
        # Ensure projects are loaded before opening dialog
        if not self.available_projects:
            await self.load_available_projects()
        
        self.add_license_dialog_open = True
        self.clear_messages()
        self.clear_add_license_form()

    def close_add_license_dialog(self):
        """Close add license dialog"""
        self.add_license_dialog_open = False
        self.clear_messages()
        self.clear_add_license_form()

    def open_renew_license_dialog(self, license_id: str):
        """Open renew license dialog"""
        # Find the license data by ID
        all_licenses = self.all_licenses if self.is_super_admin_view else self.organization_licenses
        license_data = next((lic for lic in all_licenses if lic.id == license_id), None)
        if license_data:
            self.renew_license_id = license_data.id
            self.renew_license_key = license_data.license_key
            self.renew_license_project_name = license_data.project_name
            self.renew_license_new_expires_at = ""
            self.renew_license_dialog_open = True
            self.clear_messages()

    def close_renew_license_dialog(self):
        """Close renew license dialog"""
        self.renew_license_dialog_open = False
        self.clear_messages()
        self.renew_license_id = ""
        self.renew_license_key = ""
        self.renew_license_project_name = ""
        self.renew_license_new_expires_at = ""

    def open_license_details_dialog(self, license_id: str):
        """Open license details dialog"""
        # Find the license data by ID
        all_licenses = self.all_licenses if self.is_super_admin_view else self.organization_licenses
        license_data = next((lic for lic in all_licenses if lic.id == license_id), None)
        if license_data:
            self.selected_license = license_data
            self.license_details_dialog_open = True
            self.clear_messages()

    def close_license_details_dialog(self):
        """Close license details dialog"""
        self.license_details_dialog_open = False
        self.clear_messages()
        self.selected_license = LicenseData(id="", license_key="", status=LicenseStatus.ACTIVE)

    # --- Form Management Methods ---
    def clear_add_license_form(self):
        """Clear add license form"""
        self.add_license_project_id = ""
        self.add_license_project_name = ""
        self.add_license_expires_at = ""
        self.add_license_notes = ""

    def set_add_license_project_by_name(self, project_name: str):
        """Set add license project by name"""
        self.add_license_project_name = project_name
        # Find project ID by name
        project = next((p for p in self.available_projects if p.get("name") == project_name), None)
        if project:
            self.add_license_project_id = project.get("id", "")
        else:
            self.add_license_project_id = ""
    
    def set_add_license_project_id(self, project_id: str):
        """Set add license project by ID"""
        self.add_license_project_id = project_id
        # Find project name by ID
        project = next((p for p in self.available_projects if p.get("id") == project_id), None)
        if project:
            self.add_license_project_name = project.get("name", "")
        else:
            self.add_license_project_name = ""

    # --- CRUD Operations ---
    async def add_license(self):
        """Add a new license"""
        async def create_license():
            # Validate form data
            if not self.add_license_project_id:
                self.set_error("Please select a project")
                return False
                
            if not self.add_license_expires_at:
                self.set_error("Please select an expiration date")
                return False
            
            try:
                # Parse expiration date
                expires_at = datetime.fromisoformat(self.add_license_expires_at.replace('Z', '+00:00'))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
            except ValueError:
                self.set_error("Invalid expiration date format")
                return False
            
            # Get admin user ID
            auth_state = await self.get_auth_state()
            if not auth_state.user_id:
                self.set_error("Access denied: Authentication required")
                return False
            
            # Call license service
            result = await LicenseService.issue_license(
                project_id=self.add_license_project_id,
                expires_at=expires_at,
                admin_user_id=auth_state.user_id,
                notes=self.add_license_notes
            )
            
            if result.get("success"):
                self.clear_add_license_form()
                self.close_add_license_dialog()
                await self.load_licenses()
                await self.load_license_stats()
                return True
            else:
                self.set_error(result.get("error", "Failed to issue license"))
                return False
        
        await self.handle_async_operation(
            create_license,
            "License issued successfully"
        )

    async def renew_license(self):
        """Renew an existing license"""
        async def renew_license_data():
            # Validate form data
            if not self.renew_license_id:
                self.set_error("License ID is required")
                return False
                
            if not self.renew_license_new_expires_at:
                self.set_error("Please select a new expiration date")
                return False
            
            try:
                # Parse expiration date
                new_expires_at = datetime.fromisoformat(self.renew_license_new_expires_at.replace('Z', '+00:00'))
                if new_expires_at.tzinfo is None:
                    new_expires_at = new_expires_at.replace(tzinfo=UTC)
            except ValueError as e:
                self.set_error("Invalid expiration date format")
                return False
            
            # Get admin user ID
            auth_state = await self.get_auth_state()
            if not auth_state.user_id:
                self.set_error("Access denied: Authentication required")
                return False
            
            # Call license service
            result = await LicenseService.renew_license(
                license_id=self.renew_license_id,
                new_expires_at=new_expires_at,
                admin_user_id=auth_state.user_id
            )
            
            if result.get("success"):
                self.close_renew_license_dialog()
                await self.load_licenses()
                await self.load_license_stats()
                return True
            else:
                self.set_error(result.get("error", "Failed to renew license"))
                return False
        
        await self.handle_async_operation(
            renew_license_data,
            "License renewed successfully"
        )

    def cancel_license_action(self, license_id: str):
        """Set license ID for cancellation"""
        self.selected_license_id = license_id
        
    async def cancel_license(self):
        """Cancel the selected license"""
        if not self.selected_license_id:
            return
            
        async def cancel_license_data():
            # Get admin user ID
            auth_state = await self.get_auth_state()
            if not auth_state.user_id:
                self.set_error("Access denied: Authentication required")
                return False
            
            # Call license service
            result = await LicenseService.cancel_license(
                license_id=self.selected_license_id,
                admin_user_id=auth_state.user_id
            )
            
            if result.get("success"):
                await self.load_licenses()
                await self.load_license_stats()
                self.selected_license_id = ""  # Clear after success
                return True
            else:
                self.set_error(result.get("error", "Failed to cancel license"))
                return False
        
        await self.handle_async_operation(
            cancel_license_data,
            "License cancelled successfully"
        )

    # --- Page Loading Method ---
    async def load_page_data(self):
        """Load all data needed for the license management page"""
        # Update auth state cache
        auth_state = await self.get_state(AuthState)
        self._is_super_admin = auth_state.is_super_admin
        
        # Load licenses
        await self.load_licenses()
        
        # Load available projects for licensing
        await self.load_available_projects()
        
        # Load license statistics
        await self.load_license_stats()
        
        # Load organization filter options (super admin only)
        await self.load_organization_filter_options()
    
    # --- Utility Methods ---
    def can_manage_licenses(self) -> bool:
        """Check if current user can manage licenses"""
        return self._is_super_admin

    def can_view_licenses(self) -> bool:
        """Check if current user can view licenses"""
        return self._is_super_admin  # For now, only super admin can view licenses

    def get_license_status_color(self, status: str) -> str:
        """Get color for license status badge"""
        status_colors = {
            LicenseStatus.ACTIVE: "green",
            LicenseStatus.EXPIRED: "red",
            LicenseStatus.CANCELLED: "gray"
        }
        return status_colors.get(status, "gray")

    def format_expiry_display(self, days_until_expiry: int) -> str:
        """Format expiry display text"""
        if days_until_expiry < 0:
            return f"Expired {abs(days_until_expiry)} days ago"
        elif days_until_expiry == 0:
            return "Expires today"
        elif days_until_expiry == 1:
            return "Expires tomorrow"
        else:
            return f"Expires in {days_until_expiry} days"