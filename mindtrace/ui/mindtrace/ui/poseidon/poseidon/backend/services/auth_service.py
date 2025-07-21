"""Authentication service for user management and security.

This module provides secure authentication functionality including:
- User registration with validation and password hashing
- User authentication with JWT token generation
- Email and username uniqueness validation
- Multi-tenant organization support

The service uses bcrypt for password hashing and JWT for session management,
following security best practices for web applications.
"""

from typing import Optional
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.utils.security import hash_password, verify_password, create_jwt
from poseidon.backend.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from poseidon.backend.database.models.enums import SubscriptionPlan, OrgRole


class AuthService:
    """Service class for handling authentication operations."""
    
    @staticmethod
    async def register_user(
        username: str, 
        email: str, 
        password: str, 
        organization_id: str,
        org_role: Optional[str] = None
    ) -> dict:
        """Register a new user with validation and secure password storage.
        
        Args:
            username: Unique username for the user
            email: User's email address (must be unique)
            password: Plain text password (will be hashed)
            organization_id: Required organization ID for multi-tenancy
            org_role: Organization role (defaults to "user")
            
        Returns:
            dict: Success response with user data or error information
            
        Raises:
            UserAlreadyExistsError: If email or username already exists
            ValueError: If organization doesn't exist
        """
        # Validate organization exists
        organization = await OrganizationRepository.get_by_id(organization_id)
        if not organization:
            raise ValueError("Organization not found.")
        
        # Validate email uniqueness
        if await UserRepository.get_by_email(email):
            raise UserAlreadyExistsError("Email already registered.")
            
        # Validate username uniqueness
        if await UserRepository.get_by_username(username):
            raise UserAlreadyExistsError("Username already taken.")
        
        # Hash password securely
        password_hash = hash_password(password)
        
        # Prepare user data with new structure
        user_data = {
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "organization_id": organization_id,  # Will be converted to Link in repository
            "org_role": org_role or OrgRole.USER,
            "is_active": True
        }
        
        # Create user in database
        user = await UserRepository.create(user_data)
        return {"success": True, "user": user}

    @staticmethod
    async def authenticate_user(email: str, password: str) -> dict:
        """Authenticate user credentials and generate JWT token.
        
        Args:
            email: User's email address
            password: Plain text password for verification
            
        Returns:
            dict: Success response with JWT token and user data
            
        Raises:
            UserNotFoundError: If user with email doesn't exist
            InvalidCredentialsError: If password is incorrect or user inactive
        """
        # Find user by email
        user = await UserRepository.get_by_email(email)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Check if user is active
        if not user.is_active:
            raise InvalidCredentialsError("Account is deactivated.")
        
        # Verify password against stored hash
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid password.")
        
        # Fetch linked organization using fetch_all_links instead of fetch_link
        await user.fetch_all_links()
        
        # Fetch user's project assignments
        await user.fetch_all_links()
        project_assignments = []
        for project in user.projects:
            project_assignments.append({
                "project_id": str(project.id),
                "project_name": project.name,
                "roles": ["user"]  # Default role for now
            })
        
        # Create JWT payload with user information
        payload = {
            "user_id": str(user.id), 
            "username": user.username, 
            "organization_id": str(user.organization.id),
            "org_role": user.org_role,
            "project_assignments": project_assignments
        }
        
        # Generate JWT token
        token = create_jwt(payload)
        return {"success": True, "token": token, "user": user}
    
    @staticmethod
    async def register_organization_admin(
        username: str,
        email: str,
        password: str,
        organization_id: str
    ) -> dict:
        """Register a new organization admin user.
        
        Args:
            username: Admin username
            email: Admin email
            password: Admin password
            organization_id: Organization ID
            
        Returns:
            dict: Success response with admin user data
        """
        return await AuthService.register_user(
            username=username,
            email=email,
            password=password,
            organization_id=organization_id,
            org_role=OrgRole.ADMIN
        )
    
    @staticmethod
    async def register_super_admin(
        username: str,
        email: str,
        password: str
    ) -> dict:
        """Register the first super admin user.
        
        Args:
            username: Super admin username
            email: Super admin email
            password: Super admin password
            
        Returns:
            dict: Success response with super admin user data
        """
        # Check if any super admin already exists
        existing_super_admins = await UserRepository.find_by_role(OrgRole.SUPER_ADMIN)
        if existing_super_admins:
            raise ValueError("Super admin already exists. Only one super admin is allowed.")
        
        # Create system organization for super admin
        system_org_data = {
            "name": "SYSTEM",
            "description": "System organization for super admin",
            "subscription_plan": SubscriptionPlan.ENTERPRISE,
            "is_active": True
        }
        system_org = await OrganizationRepository.create(system_org_data)
        
        return await AuthService.register_user(
            username=username,
            email=email,
            password=password,
            organization_id=str(system_org.id),
            org_role=OrgRole.SUPER_ADMIN
        )
    
    @staticmethod
    async def validate_organization_admin_key(organization_id: str, admin_key: str) -> bool:
        """Validate organization admin registration key.
        
        Args:
            organization_id: Organization ID
            admin_key: Admin registration key to validate
            
        Returns:
            bool: True if key is valid, False otherwise
        """
        organization = await OrganizationRepository.get_by_id(organization_id)
        if not organization:
            return False
        
        return organization.admin_registration_key == admin_key 