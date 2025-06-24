import reflex as rx
from poseidon.backend.services.auth_service import AuthService
from poseidon.backend.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from poseidon.backend.utils.security import decode_jwt
from typing import List

class AuthState(rx.State):
    email: str = ""
    username: str = ""
    password: str = ""
    error: str = ""
    token: str = ""
    
    user_id: str = ""
    current_username: str = ""
    user_roles: List[str] = []
    user_project: str = ""
    user_organization: str = ""
    is_authenticated: bool = False

    def check_auth(self):
        """Check if user is authenticated and decode token"""
        if self.token:
            try:
                payload = decode_jwt(self.token)
                self.user_id = payload.get("user_id", "")
                self.current_username = payload.get("username", "")
                self.user_roles = payload.get("roles", [])
                self.user_project = payload.get("project", "")
                self.user_organization = payload.get("organization", "")
                self.is_authenticated = True
            except Exception:
                self.logout()

    def has_role(self, required_role: str) -> bool:
        """Check if user has a specific role"""
        return self.is_authenticated and required_role in self.user_roles

    @rx.var
    def is_admin(self) -> bool:
        """Check if user is admin"""
        return self.has_role("admin")
    
    @rx.var
    def has_project(self) -> bool:
        """Check if user has a project assigned"""
        return self.is_authenticated and bool(self.user_project)
    
    @rx.var
    def has_organization(self) -> bool:
        """Check if user has an organization assigned"""
        return self.is_authenticated and bool(self.user_organization)
    
    @rx.var
    def user_display_name(self) -> str:
        """Get display name for the user"""
        return self.current_username if self.is_authenticated else "Guest"
    
    @rx.var
    def role_display(self) -> str:
        """Get formatted role display"""
        if not self.is_authenticated:
            return ""
        return ", ".join(self.user_roles) if self.user_roles else "No roles"
    
    def is_in_project(self, project_name: str) -> bool:
        """Check if user belongs to a specific project"""
        return self.is_authenticated and self.user_project == project_name
    
    def is_in_organization(self, org_name: str) -> bool:
        """Check if user belongs to a specific organization"""
        return self.is_authenticated and self.user_organization == org_name

    def logout(self):
        """Clear all session data"""
        self.token = ""
        self.user_id = ""
        self.current_username = ""
        self.user_roles = []
        self.user_project = ""
        self.user_organization = ""
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

    async def login(self, form_data):
        try:
            # Validate required fields
            if not form_data.get("email") or not form_data.get("password"):
                self.error = "Email and password are required."
                return
                
            result = await AuthService.authenticate_user(form_data["email"], form_data["password"])
            self.token = result["token"]
            self.check_auth()  # Decode token and set user data
            self.error = ""
            return rx.redirect("/")
        except (UserNotFoundError, InvalidCredentialsError) as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Login failed: {str(e)}"

    async def register(self, form_data):
        try:
            # Validate required fields
            if not form_data.get("username") or not form_data.get("email") or not form_data.get("password"):
                self.error = "Username, email, and password are required."
                return
                
            # Get role from form, default to "user" if not provided
            selected_role = form_data.get("role", "user")
            roles = [selected_role] if selected_role else ["user"]
            
            result = await AuthService.register_user(
                form_data["username"],
                form_data["email"],
                form_data["password"],
                roles=roles,  # Pass the roles to the service
                project=form_data.get("project", ""),
                organization=form_data.get("organization", "")
            )
            self.error = ""
            return rx.redirect("/login")
        except UserAlreadyExistsError as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Registration failed: {str(e)}" 