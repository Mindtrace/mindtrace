import reflex as rx
from poseidon.backend.services.auth_service import AuthService
from poseidon.backend.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from poseidon.backend.utils.security import decode_jwt
from typing import List, Dict, TypedDict

class ProjectAssignment(TypedDict):
    project_id: str
    roles: List[str]

class AuthState(rx.State):
    email: str = ""
    username: str = ""
    password: str = ""
    organization_id: str = ""
    error: str = ""
    token: str = ""
    field_errors: Dict[str, str] = {}
    
    # Organization discovery
    available_organizations: List[Dict[str, str]] = []
    organizations_loaded: bool = False
    
    user_id: str = ""
    current_username: str = ""
    user_organization_id: str = ""
    user_org_roles: List[str] = []
    user_project_assignments: List[ProjectAssignment] = []
    is_authenticated: bool = False

    def check_auth(self):
        """Check if user is authenticated and decode token"""
        if self.token:
            try:
                payload = decode_jwt(self.token)
                self.user_id = payload.get("user_id", "")
                self.current_username = payload.get("username", "")
                self.user_organization_id = payload.get("organization_id", "")
                self.user_org_roles = payload.get("org_roles", [])
                self.user_project_assignments = payload.get("project_assignments", [])
                self.is_authenticated = True
            except Exception:
                self.logout()

    def has_org_role(self, required_role: str) -> bool:
        """Check if user has a specific organization role"""
        return self.is_authenticated and required_role in self.user_org_roles

    def has_project_role(self, project_id: str, required_role: str) -> bool:
        """Check if user has a specific project role"""
        if not self.is_authenticated:
            return False
        for assignment in self.user_project_assignments:
            if assignment.get("project_id") == project_id:
                return required_role in assignment.get("roles", [])
        return False

    @rx.var
    def is_admin(self) -> bool:
        """Check if user is organization admin"""
        return self.has_org_role("admin")
    
    @rx.var
    def is_super_admin(self) -> bool:
        """Check if user is super admin (system-wide)"""
        return self.has_org_role("super_admin")
    
    @rx.var
    def user_display_name(self) -> str:
        """Get display name for the user"""
        return self.current_username if self.is_authenticated else "Guest"
    
    @rx.var
    def org_role_display(self) -> str:
        """Get formatted organization role display"""
        if not self.is_authenticated:
            return ""
        return ", ".join(self.user_org_roles) if self.user_org_roles else "No roles"
    
    @rx.var
    def has_projects(self) -> bool:
        """Check if user has any project assignments"""
        return self.is_authenticated and len(self.user_project_assignments) > 0
    
    @rx.var
    def project_assignments_display(self) -> List[str]:
        """Get project assignments formatted for display"""
        if not self.is_authenticated:
            return []
        result = []
        for assignment in self.user_project_assignments:
            project_id = assignment.get("project_id", "")
            roles = assignment.get("roles", [])
            roles_str = ", ".join(roles) if roles else "No roles"
            result.append(f"{project_id}: {roles_str}")
        return result
    
    def get_user_project_roles(self, project_id: str) -> List[str]:
        """Get user's roles for a specific project"""
        if not self.is_authenticated:
            return []
        for assignment in self.user_project_assignments:
            if assignment.get("project_id") == project_id:
                return assignment.get("roles", [])
        return []
    
    def is_assigned_to_project(self, project_id: str) -> bool:
        """Check if user is assigned to a specific project"""
        if not self.is_authenticated:
            return False
        return any(assignment.get("project_id") == project_id for assignment in self.user_project_assignments)
    
    async def load_available_organizations(self):
        """Load available organizations for registration."""
        try:
            from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
            orgs = await OrganizationRepository.get_all_active()
            
            self.available_organizations = [
                {
                    "id": str(org.id) if org.id else "no-id",
                    "name": org.name or "No name",
                    "description": org.description or "No description"
                }
                for org in orgs
                if org.name != "SYSTEM"  # Hide system organization from regular registration
            ]
            
            self.organizations_loaded = True
            
        except Exception as e:
            self.error = f"Failed to load organizations: {str(e)}"
            
    def validate_required_fields(self, form_data: dict, required_fields: dict) -> bool:
        """
        Validates required fields and populates field_errors.
        Returns True if all fields are valid, False if any are missing.
        """
        self.field_errors = {
            field: message
            for field, message in required_fields.items()
            if not form_data.get(field)
        }
        return not self.field_errors


    def logout(self):
        """Clear all session data"""
        self.token = ""
        self.user_id = ""
        self.current_username = ""
        self.user_organization_id = ""
        self.user_org_roles = []
        self.user_project_assignments = []
        self.is_authenticated = False
        self.error = ""
        return rx.redirect("/")
    
    def redirect_if_authenticated(self):
        """Redirect authenticated users to home"""
        if self.is_authenticated:
            return rx.redirect("/")
    
    def redirect_if_not_authenticated(self):
        """Redirect unauthenticated users to login"""
        if not self.is_authenticated:
            return rx.redirect("/login")
    
    def redirect_if_not_admin(self):
        """Redirect non-admin users"""
        if not self.is_authenticated:
            return rx.redirect("/login")
        elif not self.is_admin:
            return rx.redirect("/")
    
    def redirect_if_not_super_admin(self):
        """Redirect non-super-admin users"""
        if not self.is_authenticated:
            return rx.redirect("/login")
        elif not self.is_super_admin:
            return rx.redirect("/")

    async def login(self, form_data):
        print("Login method called with form_data:")
        # Validate required fields
        self.error = ""
        print("Full field_errors dict:", self.field_errors)
        
        if not self.validate_required_fields(form_data, {
            "email": "Email is required.",
            "password": "Password is required."
        }):
            print("Email field error:", self.field_errors.get("email", ""))
            return

        try:
            result = await AuthService.authenticate_user(form_data["email"], form_data["password"])
            self.token = result["token"]
            self.check_auth()  # Decode token and set user data
            self.error = ""
            return rx.redirect("/")
        except (UserNotFoundError, InvalidCredentialsError) as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Login failed: {str(e)}"

    def get_organization_id_by_name(self, org_name: str) -> str:
        """Get organization ID by name"""
        for org in self.available_organizations:
            if org.get("name") == org_name:
                return org.get("id", "")
        return ""

    async def register(self, form_data):
        self.error = ""

        if not self.validate_required_fields(form_data, {
            "username": "Username is required.",
            "email": "Email is required.",
            "password": "Password is required.",
            "organization_id": "Organization is required.",
        }):
            return

        # Convert organization name to ID if needed
        org_input = form_data.get("organization_id", "")
        
        # Check if it's already an ID or if we need to convert from name
        organization_id = org_input

        if organization_id == "fallback-id":
            self.field_errors["organization_id"] = "Please select a valid organization."
            return

        if not any(org.get("id") == org_input for org in self.available_organizations):
            organization_id = self.get_organization_id_by_name(org_input)
            if not organization_id:
                self.field_errors["organization_id"] = "Invalid organization selected."
                return

        try:
            # Normal registration can only create regular members (security measure)
            # Organization admins must be created through register_admin method
            result = await AuthService.register_user(
                form_data["username"],
                form_data["email"],
                form_data["password"],
                organization_id,
                org_roles=["member"]
            )
            self.error = ""
            return rx.redirect("/login")

        except UserAlreadyExistsError as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Registration failed: {str(e)}"

    async def register_admin(self, form_data):
        try:
            # Validate required fields
            if not form_data.get("username") or not form_data.get("email") or not form_data.get("password"):
                self.error = "Username, email, and password are required."
                return
            
            # Convert organization name to ID if needed
            org_input = form_data.get("organization_id", "")
            if not org_input:
                self.error = "Organization is required."
                return
            
            # Check if it's already an ID or if we need to convert from name
            organization_id = org_input
            if organization_id == "fallback-id":
                self.error = "Please select a valid organization."
                return
            if not any(org.get("id") == org_input for org in self.available_organizations):
                # It's probably a name, convert to ID
                organization_id = self.get_organization_id_by_name(org_input)
                if not organization_id:
                    self.error = "Invalid organization selected."
                    return
            
            if not form_data.get("admin_key"):
                self.error = "Admin registration key is required."
                return
            
            # Validate organization-specific admin registration key
            from poseidon.backend.services.auth_service import AuthService
            is_valid_key = await AuthService.validate_organization_admin_key(
                organization_id, 
                form_data["admin_key"]
            )
            if not is_valid_key:
                self.error = "Invalid admin registration key for this organization."
                return
                
            result = await AuthService.register_organization_admin(
                form_data["username"],
                form_data["email"],
                form_data["password"],
                organization_id
            )
            self.error = ""
            return rx.redirect("/login")
        except UserAlreadyExistsError as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Admin registration failed: {str(e)}"
    
    async def register_super_admin(self, form_data):
        """Register the first super admin user."""
        try:
            # Validate required fields
            if not form_data.get("username") or not form_data.get("email") or not form_data.get("password"):
                self.error = "Username, email, and password are required."
                return
            
            if not form_data.get("super_admin_key"):
                self.error = "Super admin key is required."
                return
            
            # Validate super admin key (master key for initial setup)
            SUPER_ADMIN_KEY = "POSEIDON_SUPER_2024"  # Change this in production!
            if form_data.get("super_admin_key") != SUPER_ADMIN_KEY:
                self.error = "Invalid super admin key."
                return
                
            from poseidon.backend.services.auth_service import AuthService
            result = await AuthService.register_super_admin(
                form_data["username"],
                form_data["email"],
                form_data["password"]
            )
            self.error = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except UserAlreadyExistsError as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Super admin registration failed: {str(e)}" 