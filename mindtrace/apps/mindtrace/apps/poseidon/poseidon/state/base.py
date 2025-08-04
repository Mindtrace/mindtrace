import reflex as rx
from typing import List, Dict, Optional, Any
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


class BaseFormState(BaseFilterState):
    """Base state with common form patterns."""
    
    def validate_required_field(self, field_value: str, field_name: str) -> bool:
        """Validate a required field and set error if empty"""
        if not field_value.strip():
            self.error = f"{field_name} is required"
            return False
        return True
    
    def validate_email(self, email: str) -> bool:
        """Basic email validation"""
        if not email or "@" not in email:
            self.error = "Valid email is required"
            return False
        return True
    
    async def handle_async_operation(self, operation_func, success_message: str):
        """Handle common async operation pattern with loading states"""
        try:
            self.loading = True
            self.clear_messages()
            
            result = await operation_func()
            
            if result:
                self.success = success_message
                return True
            else:
                self.error = "Operation failed"
                return False
                
        except Exception as e:
            self.error = f"Operation failed: {str(e)}"
            return False
        finally:
            self.loading = False


class BaseDialogState(BaseFormState):
    """Base state with common dialog patterns."""
    
    def create_dialog_methods(self, dialog_name: str):
        """Create standard dialog methods for a given dialog name"""
        # This is a helper method to document the pattern
        # Individual states should implement these methods:
        # - open_{dialog_name}_dialog()
        # - close_{dialog_name}_dialog()  
        # - set_{dialog_name}_dialog_open(open: bool)
        pass
    
    def get_dialog_control_pattern(self, dialog_name: str) -> Dict[str, Any]:
        """Get the standard dialog control pattern"""
        return {
            f"{dialog_name}_dialog_open": False,
            f"open_{dialog_name}_dialog": lambda: self._open_dialog(dialog_name),
            f"close_{dialog_name}_dialog": lambda: self._close_dialog(dialog_name),
            f"set_{dialog_name}_dialog_open": lambda open: self._set_dialog_open(dialog_name, open),
        }
    
    def _open_dialog(self, dialog_name: str):
        """Generic dialog open method"""
        setattr(self, f"{dialog_name}_dialog_open", True)
    
    def _close_dialog(self, dialog_name: str):
        """Generic dialog close method"""
        setattr(self, f"{dialog_name}_dialog_open", False)
    
    def _set_dialog_open(self, dialog_name: str, open: bool):
        """Generic dialog state setter"""
        setattr(self, f"{dialog_name}_dialog_open", open)


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