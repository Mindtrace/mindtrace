from typing import Optional
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.utils.security import hash_password, verify_password, create_jwt
from poseidon.backend.core.exceptions import (
    UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
)
from poseidon.backend.database.models.enums import SubscriptionPlan, OrgRole

SUPER_ADMIN_MASTER_KEY = "POSEIDON_SUPER_2024"  # TODO: move to env

class AuthService:
    @staticmethod
    async def register_user(
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        organization_id: str,
        org_role: Optional[str] = None,
        super_admin_key: Optional[str] = None,
    ) -> dict:
        """Register a new user or super admin (first/last name only)."""

        # Role normalization
        role_val = getattr(org_role, "value", org_role) or OrgRole.USER.value

        # Super Admin path: validate key, uniqueness, ensure SYSTEM org, ignore incoming org id
        if role_val == OrgRole.SUPER_ADMIN.value:
            if super_admin_key != SUPER_ADMIN_MASTER_KEY:
                raise ValueError("Invalid super admin key.")
            existing_super_admins = await UserRepository.find_by_role(OrgRole.SUPER_ADMIN)
            if existing_super_admins:
                raise ValueError("Super admin already exists. Only one super admin is allowed.")

            system = await OrganizationRepository.get_by_name("SYSTEM")
            if not system:
                system = await OrganizationRepository.create({
                    "name": "SYSTEM",
                    "description": "System organization for super admin",
                    "subscription_plan": SubscriptionPlan.ENTERPRISE,
                    "is_active": True,
                })
            organization_id = str(system.id)

        # Validate organization exists
        organization = await OrganizationRepository.get_by_id(organization_id)
        if not organization:
            raise ValueError("Organization not found.")

        # Uniqueness: email only
        if await UserRepository.get_by_email(email):
            raise UserAlreadyExistsError("Email already registered.")

        password_hash = hash_password(password)

        user_data = {
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
            "email": email.strip(),
            "password_hash": password_hash,
            "organization_id": organization_id,  # repo will map to Link
            "org_role": role_val,                # store as string/enum per model
            "is_active": True,
        }

        user = await UserRepository.create(user_data)
        return {"success": True, "user": user}

    @staticmethod
    async def authenticate_user(email: str, password: str) -> dict:
        user = await UserRepository.get_by_email(email)
        if not user:
            raise UserNotFoundError("User not found.")
        if not user.is_active:
            raise InvalidCredentialsError("Account is deactivated.")
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid password.")

        await user.fetch_all_links()

        project_assignments = []
        for project in getattr(user, "projects", []):
            project_assignments.append({
                "project_id": str(project.id),
                "project_name": project.name,
                "roles": ["user"],
            })

        payload = {
            "user_id": str(user.id),
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
            "organization_id": str(user.organization.id),
            "org_role": getattr(user.org_role, "value", user.org_role),
            "project_assignments": project_assignments,
        }

        token = create_jwt(payload)
        return {"success": True, "token": token, "user": user}

    # Optional helpers (still valid if you keep admin flows elsewhere)
    @staticmethod
    async def register_organization_admin(email: str, password: str, first_name: str, last_name: str, organization_id: str) -> dict:
        return await AuthService.register_user(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
            organization_id=organization_id,
            org_role=OrgRole.ADMIN,
        )

    @staticmethod
    async def validate_organization_admin_key(organization_id: str, admin_key: str) -> bool:
        organization = await OrganizationRepository.get_by_id(organization_id)
        if not organization:
            return False
        return organization.admin_registration_key == admin_key
