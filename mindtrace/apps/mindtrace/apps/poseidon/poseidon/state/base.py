import reflex as rx
from typing import List, Dict, Optional, Any, Callable, Awaitable
from poseidon.state.auth import AuthState


class BaseManagementState(rx.State):
    """Base state class for all management operations with common UI patterns."""
    
    # Common UI State
    error: str = ""
    success: str = ""
    loading: bool = False
    
    def clear_messages(self):
        """Clear success and error messages"""
        self.error = ""
        self.success = ""
    
    def set_error(self, message: str):
        """Set error message and clear success"""
        self.error = message
        self.success = ""
    
    def set_success(self, message: str):
        """Set success message and clear error"""
        self.success = message
        self.error = ""
    
    async def get_auth_state(self) -> AuthState:
        """Get the current auth state"""
        return await self.get_state(AuthState)
    
    async def check_admin_access(self) -> bool:
        """Check if user has admin access"""
        auth_state = await self.get_auth_state()
        return auth_state.is_authenticated and (auth_state.is_admin or auth_state.is_super_admin)
    
    async def check_super_admin_access(self) -> bool:
        """Check if user has super admin access"""
        auth_state = await self.get_auth_state()
        return auth_state.is_authenticated and auth_state.is_super_admin
    
    async def get_admin_organization_id(self) -> Optional[str]:
        """Get the organization ID of the current admin user"""
        auth_state = await self.get_auth_state()
        if auth_state.is_authenticated and (auth_state.is_admin or auth_state.is_super_admin):
            return auth_state.user_organization_id
        return None
    
    async def handle_async_operation(
        self, 
        operation: Callable[[], Awaitable[bool]], 
        success_message: str,
        loading_message: Optional[str] = None
    ) -> bool:
        """
        Handle common async operation pattern with loading states and error handling.
        
        Args:
            operation: Async function that returns True on success, False on failure
            success_message: Message to show on success
            loading_message: Optional loading message
            
        Returns:
            bool: True if operation succeeded, False otherwise
        """
        try:
            self.loading = True
            self.clear_messages()
            
            if loading_message:
                self.success = loading_message
            
            result = await operation()
            
            if result:
                self.set_success(success_message)
                return True
            else:
                if not self.error:  # Only set generic error if no specific error was set
                    self.set_error("Operation failed")
                return False
                
        except Exception as e:
            self.set_error(f"Operation failed: {str(e)}")
            return False
        finally:
            self.loading = False


class BaseFilterState(BaseManagementState):
    """Base state with common filtering patterns."""
    
    # Common Filters
    search_query: str = ""
    status_filter: str = "active"  # active, inactive, all
    
    def filter_by_search(self, items: List[Any], search_fields: List[str]) -> List[Any]:
        """Filter items by search query across multiple fields"""
        if not self.search_query:
            return items
        
        query_lower = self.search_query.lower()
        return [
            item for item in items
            if any(
                query_lower in str(getattr(item, field, "")).lower()
                for field in search_fields
            )
        ]
    
    def filter_by_status(self, items: List[Any], status_field: str = "is_active") -> List[Any]:
        """Filter items by status"""
        if self.status_filter == "active":
            return [item for item in items if getattr(item, status_field, True)]
        elif self.status_filter == "inactive":
            return [item for item in items if not getattr(item, status_field, True)]
        # "all" shows all items
        return items
    
    def set_search_query(self, query: str):
        """Set search query"""
        self.search_query = query
    
    def set_status_filter(self, status: str):
        """Set status filter"""
        self.status_filter = status
    
    def clear_filters(self):
        """Clear all filters"""
        self.search_query = ""
        self.status_filter = "active"


class BaseFormState(BaseFilterState):
    """Base state with common form patterns."""
    
    def validate_required_field(self, field_value: str, field_name: str) -> bool:
        """Validate a required field and set error if empty"""
        if not field_value or not field_value.strip():
            self.set_error(f"{field_name} is required")
            return False
        return True
    
    def validate_email(self, email: str) -> bool:
        """Basic email validation"""
        if not email or "@" not in email:
            self.set_error("Valid email is required")
            return False
        return True
    
    def validate_positive_integer(self, value: str, field_name: str) -> bool:
        """Validate positive integer field"""
        if not value.isdigit() or int(value) <= 0:
            self.set_error(f"{field_name} must be a positive number")
            return False
        return True


class BaseDialogState(BaseFormState):
    """Base state with common dialog patterns."""
    
    def open_dialog(self, dialog_name: str):
        """Generic dialog open method"""
        setattr(self, f"{dialog_name}_dialog_open", True)
        self.clear_messages()
    
    def close_dialog(self, dialog_name: str):
        """Generic dialog close method"""
        setattr(self, f"{dialog_name}_dialog_open", False)
        self.clear_messages()
    
    def set_dialog_open(self, dialog_name: str, open: bool):
        """Generic dialog state setter"""
        setattr(self, f"{dialog_name}_dialog_open", open)
        if not open:
            self.clear_messages()


class BasePaginationState(BaseDialogState):
    """Base state with pagination patterns."""
    
    # Pagination
    current_page: int = 1
    items_per_page: int = 10
    
    def calculate_total_pages(self, items: List[Any]) -> int:
        """Calculate total number of pages for given items"""
        if not items:
            return 1
        return (len(items) + self.items_per_page - 1) // self.items_per_page
    
    def next_page(self):
        """Go to next page"""
        if self.current_page < self.total_pages:
            self.current_page += 1
    
    def previous_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
    
    def go_to_page(self, page: int):
        """Go to specific page"""
        if 1 <= page <= self.total_pages:
            self.current_page = page
    
    def get_paginated_items(self, items: List[Any]) -> List[Any]:
        """Get items for current page"""
        start_index = (self.current_page - 1) * self.items_per_page
        end_index = start_index + self.items_per_page
        return items[start_index:end_index]


class RoleBasedAccessMixin:
    """Mixin for role-based access control patterns."""
    
    def can_edit_item(self, target_item_id: str, current_user_id: str, is_admin: bool, is_super_admin: bool) -> bool:
        """Check if current user can edit the target item"""
        # No one can edit themselves (self-protection)
        if current_user_id == target_item_id:
            return False
            
        # Super admins can edit anyone except themselves
        if is_super_admin:
            return True
            
        # Regular admins can edit other items except themselves
        if is_admin:
            return True
            
        # Regular users cannot edit anyone
        return False
    
    def can_deactivate_item(self, target_item_id: str, current_user_id: str, is_admin: bool, is_super_admin: bool) -> bool:
        """Check if current user can deactivate the target item"""
        # Same logic as edit for most cases
        return self.can_edit_item(target_item_id, current_user_id, is_admin, is_super_admin)
    
    def can_manage_organization(self, is_super_admin: bool) -> bool:
        """Check if user can manage organizations"""
        return is_super_admin
    
    def can_manage_projects(self, is_admin: bool, is_super_admin: bool) -> bool:
        """Check if user can manage projects"""
        return is_admin or is_super_admin
    
    def can_manage_users(self, is_admin: bool, is_super_admin: bool) -> bool:
        """Check if user can manage users"""
        return is_admin or is_super_admin 