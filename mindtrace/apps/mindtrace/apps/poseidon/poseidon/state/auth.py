import reflex as rx
from typing import List, Dict
from poseidon.backend.services.auth_service import AuthService
from poseidon.backend.core.exceptions import (
    UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
)
from poseidon.backend.utils.security import decode_jwt
from poseidon.backend.database.models.enums import OrgRole

class ProjectAssignment:
    project_id: str
    roles: List[str]

class AuthState(rx.State):
    # --- form fields ---
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    password: str = ""
    organization_id: str = ""
    is_register_super_admin: bool = False

    # --- session / ui ---
    error: str = ""
    token: str = ""
    available_organizations: List[Dict[str, str]] = []
    organizations_loaded: bool = False

    # --- decoded token/user ---
    user_id: str = ""
    current_first_name: str = ""
    current_last_name: str = ""
    user_organization_id: str = ""
    user_org_role: str = ""  # string in JWT
    user_project_assignments: List[ProjectAssignment] = []
    is_authenticated: bool = False

    # -------- helpers --------
    def _role_eq(self, a, b) -> bool:
        av = getattr(a, "value", a)
        bv = getattr(b, "value", b)
        return str(av) == str(bv)

    def check_auth(self):
        if self.token:
            try:
                payload = decode_jwt(self.token)
                self.user_id = payload.get("user_id", "")
                self.current_first_name = payload.get("first_name", "")
                self.current_last_name = payload.get("last_name", "")
                self.user_organization_id = payload.get("organization_id", "")
                self.user_org_role = payload.get("org_role", "")
                self.user_project_assignments = payload.get("project_assignments", [])
                self.is_authenticated = True
            except Exception:
                self.logout()

    def has_org_role(self, required_role: str) -> bool:
        return self.is_authenticated and self._role_eq(self.user_org_role, required_role)

    def has_project_role(self, project_id: str, required_role: str) -> bool:
        if not self.is_authenticated:
            return False
        for a in self.user_project_assignments:
            if a.get("project_id") == project_id:
                return required_role in a.get("roles", [])
        return False

    @rx.var
    def is_admin(self) -> bool:
        return self.has_org_role(OrgRole.ADMIN.value)

    @rx.var
    def is_super_admin(self) -> bool:
        return self.has_org_role(OrgRole.SUPER_ADMIN.value)

    @rx.var
    def is_user(self) -> bool:
        return self.has_org_role(OrgRole.USER.value)

    @rx.var
    def role_display(self) -> str:
        if self.is_super_admin:
            return "Super Admin"
        elif self.is_admin:
            return "Admin"
        elif self.is_user:
            return "User"
        return "Unknown"

    @rx.var
    def has_project_assignments(self) -> bool:
        return self.is_authenticated and len(self.user_project_assignments) > 0

    @rx.var
    def project_assignments_display(self) -> List[str]:
        if not self.is_authenticated:
            return []
        return [
            f"{a.get('project_name','Unknown Project')} ({', '.join(a.get('roles', []))})"
            for a in self.user_project_assignments
        ]

    @rx.var
    def current_project_display(self) -> str:
        if not self.has_project_assignments:
            return "No projects assigned"
        for a in self.user_project_assignments:
            return a.get("project_name", "Unknown Project")
        return "No projects assigned"

    def is_assigned_to_project(self, project_id: str) -> bool:
        return any(a.get("project_id") == project_id for a in self.user_project_assignments)

    @rx.var
    def initials(self) -> str:
        # Prefer first/last; fall back to email local-part
        fn, ln = (self.current_first_name or "").strip(), (self.current_last_name or "").strip()
        if fn and ln:
            return (fn[0] + ln[0]).upper()
        if fn:
            return fn[:2].upper()
        if ln:
            return ln[:2].upper()
        source = self.email.split("@")[0] if "@" in self.email else self.email
        clean = "".join(ch for ch in source if ch.isalnum())
        if len(clean) >= 2:
            return clean[:2].upper()
        return (clean[:1].upper() or "U")

    async def load_available_organizations(self):
        try:
            from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
            orgs = await OrganizationRepository.get_all_active()
            self.available_organizations = [
                {
                    "id": str(org.id) if org.id else "no-id",
                    "name": org.name or "No name",
                    "description": org.description or "No description",
                }
                for org in orgs
                if org.name != "SYSTEM"
            ]
            self.organizations_loaded = True
        except Exception as e:
            self.error = f"Failed to load organizations: {str(e)}"

    def logout(self):
        self.token = ""
        self.user_id = ""
        self.current_first_name = ""
        self.current_last_name = ""
        self.user_organization_id = ""
        self.user_org_role = ""
        self.user_project_assignments = []
        self.is_authenticated = False
        self.error = ""
        return rx.redirect("/")

    def redirect_if_authenticated(self):
        if self.is_authenticated:
            return rx.redirect("/")

    def redirect_if_not_authenticated(self):
        if not self.is_authenticated:
            return rx.redirect("/login")

    def redirect_if_not_admin(self):
        if not self.is_authenticated:
            return rx.redirect("/login")
        elif not self.is_admin:
            return rx.redirect("/")

    def redirect_if_not_super_admin(self):
        if not self.is_authenticated:
            return rx.redirect("/login")
        elif not self.is_super_admin:
            return rx.redirect("/")

    async def login(self, form_data):
        try:
            if not form_data.get("email") or not form_data.get("password"):
                self.error = "Email and password are required."
                return
            result = await AuthService.authenticate_user(form_data["email"], form_data["password"])
            self.token = result["token"]
            self.check_auth()
            self.error = ""
            return rx.redirect("/profile")
        except (UserNotFoundError, InvalidCredentialsError) as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Login failed: {str(e)}"

    def get_organization_id_by_name(self, org_name: str) -> str:
        for org in self.available_organizations:
            if org.get("name") == org_name:
                return org.get("id", "")
        return ""

    async def register(self, form_data):
        """Unified registration: normal user or super admin based on checkbox."""
        try:
            first_name = (form_data.get("first_name") or "").strip()
            last_name = (form_data.get("last_name") or "").strip()
            email = (form_data.get("email") or "").strip()
            password = form_data.get("password", "")
            confirm = form_data.get("confirm_password", "")

            if not first_name or not last_name:
                self.error = "First name and last name are required."
                return
            if not email or not password or not confirm:
                self.error = "Email, password, and confirm password are required."
                return
            if password != confirm:
                self.error = "Passwords do not match."
                return

            if self.is_register_super_admin:
                super_key = form_data.get("super_admin_key", "")
                if not super_key:
                    self.error = "Super admin key is required."
                    return

                await AuthService.register_user(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                    organization_id="",                 # ignored for SA; service will ensure SYSTEM
                    org_role=OrgRole.SUPER_ADMIN,
                    super_admin_key=super_key,
                )
                self.error = ""
                return rx.redirect("/login")

            # Normal user path
            org_input = form_data.get("organization_id", "")
            if not org_input:
                self.error = "Organization is required."
                return
            if org_input == "fallback-id":
                self.error = "Please select a valid organization."
                return
            organization_id = org_input
            if not any(org.get("id") == org_input for org in self.available_organizations):
                organization_id = self.get_organization_id_by_name(org_input)
                if not organization_id:
                    self.error = "Invalid organization selected."
                    return

            await AuthService.register_user(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                organization_id=organization_id,
                org_role=OrgRole.USER,
            )
            self.error = ""
            return rx.redirect("/login")

        except UserAlreadyExistsError as e:
            self.error = str(e)
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Registration failed: {str(e)}"
