"""Authentication service for user management and security.

This module provides secure authentication functionality including:
- User registration with validation and password hashing
- User authentication with JWT token generation
- Email and username uniqueness validation
- Role-based access control support

The service uses bcrypt for password hashing and JWT for session management,
following security best practices for web applications.
"""

from typing import Optional
from poseidon.backend.database.repositories.user_repository import UserRepository
from poseidon.backend.utils.security import hash_password, verify_password, create_jwt
from poseidon.backend.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError


class AuthService:
    """Service class for handling authentication operations."""
    
    @staticmethod
    async def register_user(
        username: str, 
        email: str, 
        password: str, 
        roles: Optional[list] = None, 
        project: str = "", 
        organization: str = ""
    ) -> dict:
        """Register a new user with validation and secure password storage.
        
        Args:
            username: Unique username for the user
            email: User's email address (must be unique)
            password: Plain text password (will be hashed)
            roles: List of user roles (defaults to empty list)
            project: Optional project association
            organization: Optional organization association
            
        Returns:
            dict: Success response with user data or error information
            
        Raises:
            UserAlreadyExistsError: If email or username already exists
        """
        # Validate email uniqueness
        if await UserRepository.get_by_email(email):
            raise UserAlreadyExistsError("Email already registered.")
            
        # Validate username uniqueness
        if await UserRepository.get_by_username(username):
            raise UserAlreadyExistsError("Username already taken.")
        
        # Hash password securely
        password_hash = hash_password(password)
        
        # Prepare user data
        user_data = {
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "roles": roles or [],
            "project": project,
            "organization": organization,
        }
        
        # Create user in database
        user = await UserRepository.create_user(user_data)
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
            InvalidCredentialsError: If password is incorrect
        """
        # Find user by email
        user = await UserRepository.get_by_email(email)
        if not user:
            raise UserNotFoundError("User not found.")
        
        # Verify password against stored hash
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid password.")
        
        # Create JWT payload with user information
        payload = {
            "user_id": str(user.id), 
            "username": user.username, 
            "roles": user.roles,
            "project": user.project or "",
            "organization": user.organization or ""
        }
        
        # Generate JWT token
        token = create_jwt(payload)
        return {"success": True, "token": token, "user": user} 