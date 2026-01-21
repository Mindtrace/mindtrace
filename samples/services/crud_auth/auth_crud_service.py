#!/usr/bin/env python3
"""
Authenticated CRUD Service Example - Demonstrates Create, Read, Update, Delete operations
with authentication and MongoDB storage.

This service shows how to build a complete authenticated CRUD API using mindtrace-services
with MongoDB for persistent storage.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Optional, Union

import jwt
from fastapi import Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, EmailStr, Field, field_validator

from mindtrace.core import TaskSchema
from mindtrace.database import MindtraceDocument, MongoMindtraceODM
from mindtrace.services import Scope, Service

# ============================================================================
# MongoDB Models
# ============================================================================


class User(MindtraceDocument):
    """User model for MongoDB with password hashing.

    Uses Argon2 password hashing via pwdlib
    """

    name: str = Field(description="User's full name")
    email: EmailStr = Field(description="User's email address")
    hashed_password: str = Field(description="Hashed password using Argon2")
    age: int = Field(ge=0, description="User's age")
    skills: list[str] = Field(default_factory=list, description="User skills")
    disabled: bool = Field(default=False, description="Whether user is disabled")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        """Settings for the User model."""

        name = "users"
        use_cache = False


# ============================================================================
# API Input/Output Models
# ============================================================================


class UserCreateInput(BaseModel):
    """Input model for creating a user."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(description="Plain text password (will be hashed)", min_length=8)
    age: int = Field(ge=0)
    skills: list[str] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength.

        Requirements:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLoginInput(BaseModel):
    """Input model for user login (uses OAuth2PasswordRequestForm)."""

    username: str = Field(description="Email address (used as username)")
    password: str = Field(description="Plain text password")


class UserUpdateInput(BaseModel):
    """Input model for updating a user."""

    user_id: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    age: Optional[int] = Field(None, ge=0)
    skills: Optional[list[str]] = None


class UserOutput(BaseModel):
    """Output model for a user (password excluded)."""

    id: str
    name: str
    email: str
    age: int
    skills: list[str]
    disabled: bool
    created_at: str
    updated_at: str


class LoginForm:
    """Custom login form that uses 'email' instead of 'username' for better UX in Swagger UI."""

    def __init__(
        self,
        email: str = Form(..., description="User email address", examples=["user@example.com"]),
        password: str = Form(..., description="User password"),
    ):
        self.email = email
        self.password = password


class Token(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str


class UserIDInput(BaseModel):
    """Input model for operations requiring a user ID."""

    user_id: str


class UserListOutput(BaseModel):
    """Output model for listing users."""

    users: list[UserOutput]
    total: int


class UserSearchInput(BaseModel):
    """Input model for searching users."""

    query: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    skill: Optional[str] = None
    limit: int = 10
    offset: int = 0


# ============================================================================
# Task Schemas
# ============================================================================

create_user_schema = TaskSchema(
    name="create_user",
    input_schema=UserCreateInput,
    output_schema=UserOutput,
)

get_user_schema = TaskSchema(
    name="get_user",
    input_schema=None,  # Uses query parameter: user_id
    output_schema=UserOutput,
)

update_user_schema = TaskSchema(
    name="update_user",
    input_schema=UserUpdateInput,
    output_schema=UserOutput,
)

delete_user_schema = TaskSchema(
    name="delete_user",
    input_schema=None,  # Uses query parameter: user_id
    output_schema=UserOutput,
)

list_users_schema = TaskSchema(
    name="list_users",
    input_schema=None,  # No input required
    output_schema=UserListOutput,
)

search_users_schema = TaskSchema(
    name="search_users",
    input_schema=None,  # Uses query parameters
    output_schema=UserListOutput,
)

login_schema = TaskSchema(
    name="login",
    input_schema=None,  # Uses custom LoginForm with email field
    output_schema=Token,
)


# ============================================================================
# Password Hashing and Token Management
# ============================================================================

# Secret key for JWT
# In production, ALWAYS set JWT_SECRET via environment variable
# Generate with: openssl rand -hex 32
# For this sample, we use a default value if not set, but this should NEVER be used in production
JWT_SECRET = os.getenv("JWT_SECRET", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
if not os.getenv("JWT_SECRET"):
    import warnings

    warnings.warn(
        "WARNING: Using default JWT_SECRET. This is INSECURE for production! "
        "Set JWT_SECRET environment variable: export JWT_SECRET=$(openssl rand -hex 32)",
        UserWarning,
        stacklevel=3,
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing using pwdlib with Argon2 (recommended by FastAPI)
# See: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#why-use-password-hashing
password_hash = PasswordHash.recommended()

# OAuth2 scheme for token endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Uses pwdlib with Argon2 as recommended by FastAPI.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2.

    Uses pwdlib with Argon2 as recommended by FastAPI.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return password_hash.hash(password)


def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    """Create a JWT access token.

    Args:
        data: Data to encode in token (typically {"sub": username})
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


# Module-level state for service instance
class _ServiceInstanceState:
    """State class to hold service instance for token verification."""

    def __init__(self):
        self.instance: Optional["AuthenticatedCRUDService"] = None

    def set(self, service: "AuthenticatedCRUDService") -> None:
        """Set the service instance."""
        self.instance = service

    def get(self) -> Optional["AuthenticatedCRUDService"]:
        """Get the service instance."""
        return self.instance


_service_state = _ServiceInstanceState()


def set_service_instance(service: "AuthenticatedCRUDService") -> None:
    """Set the service instance for token verification.

    This allows verify_token to access the database to validate users.
    """
    _service_state.set(service)


async def verify_token_async(token: str) -> dict:
    """Verify JWT token and return user information (async version).

    This function validates:
    1. Token signature and expiration
    2. User still exists in database
    3. User is not disabled

    Args:
        token: JWT token string

    Returns:
        dict: User information from token payload

    Raises:
        HTTPException: If token is invalid or user is disabled/deleted
    """
    try:
        # Decode and verify JWT token
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Extract user information from token
        # Token contains: user_id, email (and optionally username)
        user_id = payload.get("user_id")
        email = payload.get("email") or payload.get("sub")  # Support both formats

        if not user_id and not email:
            raise HTTPException(status_code=401, detail="Invalid token: missing user identifier")

        # Validate user still exists and is not disabled
        service_instance = _service_state.get()
        if service_instance:
            try:
                # Try to find user by ID first, then by email
                if user_id:
                    user = await service_instance.db.user.get(user_id)
                elif email:
                    users = await service_instance.db.user.find({"email": email})
                    if not users:
                        raise HTTPException(status_code=401, detail="Invalid token: user not found")
                    user = users[0]
                else:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid token: missing user identifier",
                    )

                # Check if user is disabled
                if user.disabled:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid token: user account is disabled",
                    )

                # Return validated user information
                return {
                    "user_id": str(user.id),
                    "email": user.email,
                    "username": user.email,  # Use email as username
                }
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token: user validation failed",
                ) from exc
        else:
            # Fallback if service instance not set (should not happen in production)
            return {
                "user_id": user_id,
                "email": email,
                "username": email or "unknown",
            }
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except HTTPException:
        raise
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token verification failed") from exc


# ============================================================================
# Authenticated CRUD Service
# ============================================================================


class AuthenticatedCRUDService(Service):
    """Service demonstrating authenticated CRUD operations with MongoDB storage."""

    # Default MongoDB URI - database is created on demand
    # Credentials detected from running MongoDB container (inspectra_mongo)
    # If using a different MongoDB instance, update these credentials accordingly
    DEFAULT_MONGO_URI = "mongodb://admin:adminpassword@localhost:27017/?authSource=admin"
    DEFAULT_MONGO_DB_NAME = "auth_crud_db"

    def __init__(
        self,
        *,
        mongo_uri: str | None = None,
        mongo_db_name: str | None = None,
        **kwargs,
    ):
        """Initialize the authenticated CRUD service.

        Args:
            mongo_uri: MongoDB connection URI (defaults to DEFAULT_MONGO_URI)
            mongo_db_name: MongoDB database name (defaults to DEFAULT_MONGO_DB_NAME)
            **kwargs: Additional arguments passed to Service
        """
        super().__init__(**kwargs)

        # Use defaults if not provided (database is created on demand)
        mongo_uri = mongo_uri or self.DEFAULT_MONGO_URI
        mongo_db_name = mongo_db_name or self.DEFAULT_MONGO_DB_NAME

        # Initialize MongoDB ODM with User model
        self.db = MongoMindtraceODM(
            models={"user": User},
            db_uri=mongo_uri,
            db_name=mongo_db_name,
            allow_index_dropping=True,
        )

        # Set service instance for token verification
        set_service_instance(self)

        # Set up token verification (use async version)
        self.set_token_verifier(verify_token_async)

        # Allows endpoints to inject the current user via Depends()
        self._get_current_user = self.get_current_user_dependency()

        # Register all CRUD endpoints with authentication
        # Public endpoints (no auth required)
        self.add_endpoint(
            "login",
            self.login,
            schema=login_schema,
            methods=["POST"],
            scope=Scope.PUBLIC,
        )
        self.add_endpoint(
            "list_users",
            self.list_users,
            schema=list_users_schema,
            methods=["GET"],
            scope=Scope.PUBLIC,
        )
        self.add_endpoint(
            "search_users",
            self.search_users,
            schema=search_users_schema,
            methods=["GET"],
            scope=Scope.PUBLIC,
        )

        self.add_endpoint(
            "create_user",
            self.create_user,
            schema=create_user_schema,
            methods=["POST"],
            scope=Scope.PUBLIC,
        )
        # Get the current user dependency for injection into endpoint methods
        get_current_user = self._get_current_user

        # Create a wrapper that properly injects the dependency for GET requests
        async def get_user_wrapper(user_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
            return await self.get_user(user_id, current_user)

        self.add_endpoint(
            "get_user",
            get_user_wrapper,
            schema=get_user_schema,
            methods=["GET"],
            scope=Scope.AUTHENTICATED,
        )

        # Create wrappers that properly inject the dependency for PUT/DELETE requests
        async def update_user_wrapper(
            payload: UserUpdateInput, current_user: Annotated[dict, Depends(get_current_user)]
        ):
            return await self.update_user(payload, current_user)

        async def delete_user_wrapper(user_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
            return await self.delete_user(user_id, current_user)

        self.add_endpoint(
            "update_user",
            update_user_wrapper,
            schema=update_user_schema,
            methods=["PUT"],
            scope=Scope.AUTHENTICATED,
        )
        self.add_endpoint(
            "delete_user",
            delete_user_wrapper,
            schema=delete_user_schema,
            methods=["DELETE"],
            scope=Scope.AUTHENTICATED,
        )

    async def login(self, form_data: LoginForm = Depends()) -> Token:
        """Login endpoint to authenticate user and get access token.

        Args:
            form_data: Login form with email and password

        Returns:
            Token with access_token and token_type

        Raises:
            HTTPException: If credentials are invalid
        """
        # Find user by email
        users = await self.db.user.find({"email": form_data.email})
        if not users:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = users[0]

        # Verify password using Argon2
        if not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is disabled
        if user.disabled:
            raise HTTPException(status_code=400, detail="Inactive user")

        # Create access token with user information
        # Include user_id and email for proper token verification
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": user.email,  # Subject (email) as per JWT spec
                "user_id": str(user.id),  # User ID for authorization checks
                "email": user.email,  # Email for convenience
            },
            expires_delta=access_token_expires,
        )

        return Token(access_token=access_token, token_type="bearer")

    async def create_user(self, payload: UserCreateInput) -> UserOutput:
        """Create a new user (authenticated).

        Password is hashed using Argon2 before storage.

        Args:
            payload: User creation data (includes plain text password)

        Returns:
            Created user with generated ID and timestamps (password excluded)
        """
        # Check if email already exists
        existing = await self.db.user.find({"email": payload.email})
        if existing:
            raise HTTPException(status_code=400, detail="An account with this email address already exists.")

        # Hash password using Argon2
        hashed_password = get_password_hash(payload.password)

        # Create user document
        user_data = {
            "name": payload.name,
            "email": payload.email,
            "hashed_password": hashed_password,
            "age": payload.age,
            "skills": payload.skills,
            "disabled": False,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        user = await self.db.user.insert(user_data)

        return UserOutput(
            id=str(user.id),
            name=user.name,
            email=user.email,
            age=user.age,
            skills=user.skills,
            disabled=user.disabled,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )

    async def get_user(self, user_id: str, current_user: dict) -> UserOutput:
        """Get a user by ID (authenticated).

        Users can view any user's profile in this example.
        In production, you might want to restrict this to only allow users
        to view their own profile or implement role-based access control.

        Args:
            user_id: The ID of the user to retrieve
            current_user: Current authenticated user (from token) - available for future authorization checks

        Returns:
            User data

        Raises:
            HTTPException: If user not found
        """
        # current_user is available for future authorization checks
        _ = current_user  # Acknowledge parameter for now
        try:
            user = await self.db.user.get(user_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="User not found") from exc

        return UserOutput(
            id=str(user.id),
            name=user.name,
            email=user.email,
            age=user.age,
            skills=user.skills,
            disabled=user.disabled,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )

    async def update_user(
        self,
        payload: UserUpdateInput,
        current_user: dict,
    ) -> UserOutput:
        """Update an existing user (authenticated).

        Users can only update their own profile.

        Args:
            payload: Update data (partial) including user_id
            current_user: Current authenticated user (from token)

        Returns:
            Updated user data

        Raises:
            HTTPException: If user not found or unauthorized
        """
        # Authorization check: users can only update their own profile
        current_user_id = current_user.get("user_id")
        if current_user_id != payload.user_id:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: You can only update your own profile",
            )

        try:
            user = await self.db.user.get(payload.user_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="User not found") from exc

        # Update only provided fields
        if payload.name is not None:
            user.name = payload.name
        if payload.email is not None:
            # Check if new email already exists
            existing = await self.db.user.find({"email": payload.email})
            if existing and str(existing[0].id) != payload.user_id:
                raise HTTPException(status_code=400, detail="An account with this email address already exists.")
            user.email = payload.email
        if payload.age is not None:
            user.age = payload.age
        if payload.skills is not None:
            user.skills = payload.skills

        user.updated_at = datetime.now(UTC)
        updated_user = await self.db.user.update(user)

        return UserOutput(
            id=str(updated_user.id),
            name=updated_user.name,
            email=updated_user.email,
            age=updated_user.age,
            skills=updated_user.skills,
            disabled=updated_user.disabled,
            created_at=updated_user.created_at.isoformat(),
            updated_at=updated_user.updated_at.isoformat(),
        )

    async def delete_user(self, user_id: str, current_user: dict) -> UserOutput:
        """Delete a user by ID (authenticated).

        Users can only delete their own account.

        Args:
            user_id: The ID of the user to delete
            current_user: Current authenticated user (from token)

        Returns:
            Deleted user data

        Raises:
            HTTPException: If user not found or unauthorized
        """
        # Authorization check: users can only delete their own account
        current_user_id = current_user.get("user_id")
        if current_user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: You can only delete your own account",
            )

        try:
            user = await self.db.user.get(user_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="User not found") from exc

        user_output = UserOutput(
            id=str(user.id),
            name=user.name,
            email=user.email,
            age=user.age,
            skills=user.skills,
            disabled=user.disabled,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )

        await self.db.user.delete(user_id)

        return user_output

    async def list_users(self) -> UserListOutput:
        """List all users (public endpoint).

        Returns:
            List of all users
        """
        users = await self.db.user.all()

        user_outputs = [
            UserOutput(
                id=str(user.id),
                name=user.name,
                email=user.email,
                age=user.age,
                skills=user.skills,
                disabled=user.disabled,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat(),
            )
            for user in users
        ]

        return UserListOutput(users=user_outputs, total=len(user_outputs))

    async def search_users(
        self,
        query: Optional[str] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        skill: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> UserListOutput:
        """Search users with filters (public endpoint).

        Args:
            query: Text to search in name and email
            min_age: Minimum age filter
            max_age: Maximum age filter
            skill: Filter by skill
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            Filtered list of users
        """
        # Get all users first (for filtering)
        all_users = await self.db.user.all()
        filtered_users = []

        for user in all_users:
            match = True

            # Text search in name or email
            if query:
                query_lower = query.lower()
                if not (query_lower in user.name.lower() or query_lower in user.email.lower()):
                    match = False

            # Age filters
            if min_age is not None and user.age < min_age:
                match = False
            if max_age is not None and user.age > max_age:
                match = False

            # Skill filter
            if skill and skill not in user.skills:
                match = False

            if match:
                filtered_users.append(user)

        # Convert to output format
        user_outputs = [
            UserOutput(
                id=str(user.id),
                name=user.name,
                email=user.email,
                age=user.age,
                skills=user.skills,
                disabled=user.disabled,
                created_at=user.created_at.isoformat(),
                updated_at=user.updated_at.isoformat(),
            )
            for user in filtered_users
        ]

        # Apply pagination
        total = len(user_outputs)
        paginated_results = user_outputs[offset : offset + limit]

        return UserListOutput(users=paginated_results, total=total)
