"""Integration tests for authentication features in mindtrace-services."""

from typing import Annotated

import pytest
from fastapi import Depends, HTTPException
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Scope, Service
from mindtrace.services.core.types import EndpointsOutput

# ============================================================================
# Simple Test Service with Authentication
# ============================================================================


class UserInfo(BaseModel):
    """User information model."""

    user_id: str
    email: str
    name: str


class PublicDataOutput(BaseModel):
    """Output for public endpoint."""

    message: str
    data: str


class ProtectedDataOutput(BaseModel):
    """Output for protected endpoint."""

    message: str
    user_id: str
    email: str


class LoginInput(BaseModel):
    """Input model for login endpoint."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"


# Simple in-memory user store for testing
_test_users = {
    "user1@example.com": {"user_id": "user1", "name": "Test User 1", "password": "TestPass123"},
    "user2@example.com": {"user_id": "user2", "name": "Test User 2", "password": "TestPass456"},
}

# Simple token store (in production, use proper JWT)
_test_tokens = {}


def create_test_token(user_id: str, email: str) -> str:
    """Create a simple test token (in production, use JWT)."""
    import hashlib
    import time

    token_data = f"{user_id}:{email}:{time.time()}"
    token = hashlib.sha256(token_data.encode()).hexdigest()
    _test_tokens[token] = {"user_id": user_id, "email": email}
    return token


def verify_test_token(token: str) -> dict:
    """Verify test token and return user info."""
    if token not in _test_tokens:
        raise HTTPException(status_code=401, detail="Invalid token")
    return _test_tokens[token]


class AuthenticatedTestService(Service):
    """Simple authenticated service for integration testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set up token verification
        self.set_token_verifier(verify_test_token)
        get_current_user = self.get_current_user_dependency()

        # Public endpoints
        public_data_schema = TaskSchema(
            name="public_data",
            input_schema=None,
            output_schema=PublicDataOutput,
        )
        self.add_endpoint("public_data", self.get_public_data, schema=public_data_schema, scope=Scope.PUBLIC)

        login_schema = TaskSchema(
            name="login",
            input_schema=LoginInput,
            output_schema=TokenResponse,
        )
        self.add_endpoint("login", self.login, schema=login_schema, scope=Scope.PUBLIC)

        # Authenticated endpoints
        protected_data_schema = TaskSchema(
            name="protected_data",
            input_schema=None,
            output_schema=ProtectedDataOutput,
        )
        self.add_endpoint(
            "protected_data", self.get_protected_data, schema=protected_data_schema, scope=Scope.AUTHENTICATED
        )

        # Authenticated endpoint with user injection
        user_profile_schema = TaskSchema(
            name="user_profile",
            input_schema=None,
            output_schema=UserInfo,
        )

        # Create wrapper to properly inject user dependency
        async def user_profile_wrapper(current_user: Annotated[dict, Depends(get_current_user)]):
            return await self.get_user_profile(current_user)

        self.add_endpoint("user_profile", user_profile_wrapper, schema=user_profile_schema, scope=Scope.AUTHENTICATED)

    def login(self, payload: LoginInput) -> TokenResponse:
        """Login endpoint - public, returns token."""
        if payload.email not in _test_users:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user = _test_users[payload.email]
        if user["password"] != payload.password:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_test_token(user["user_id"], payload.email)
        return TokenResponse(access_token=token)

    def get_public_data(self) -> PublicDataOutput:
        """Public endpoint - no authentication required."""
        return PublicDataOutput(message="This is public data", data="Anyone can access this")

    async def get_protected_data(self) -> ProtectedDataOutput:
        """Protected endpoint - requires authentication."""
        # This endpoint is protected by scope=Scope.AUTHENTICATED
        # The token verification happens automatically via the auth dependency
        # But we don't have access to user info here unless we inject it
        return ProtectedDataOutput(
            message="This is protected data",
            user_id="unknown",  # We can't get user info without injection
            email="unknown",
        )

    async def get_user_profile(self, current_user: dict) -> UserInfo:
        """Protected endpoint with user injection - requires authentication and provides user info."""
        # current_user is automatically injected via Depends(get_current_user_dependency())
        return UserInfo(
            user_id=current_user["user_id"],
            email=current_user["email"],
            name=_test_users.get(current_user["email"], {}).get("name", "Unknown"),
        )


# ============================================================================
# Integration Tests
# ============================================================================


class TestAuthIntegration:
    """Integration tests for authentication features."""

    @pytest.mark.asyncio
    async def test_public_endpoint_accessible_without_auth(self, auth_service_manager):
        """Test that public endpoints work without authentication."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Public endpoint should work without token
        result = auth_service_manager.public_data()
        assert result.message == "This is public data"
        assert result.data == "Anyone can access this"

    @pytest.mark.asyncio
    async def test_protected_endpoint_requires_auth(self, auth_service_manager):
        """Test that protected endpoints require authentication."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Try to access protected endpoint without token - should fail
        # Note: The connection manager might handle this differently
        # We'll test via direct HTTP request
        import httpx

        base_url = str(auth_service_manager.url).rstrip("/")
        response = httpx.post(f"{base_url}/protected_data", timeout=5.0)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_and_token_usage(self, auth_service_manager):
        """Test login flow and using token for authenticated requests."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Login to get token
        token_response = auth_service_manager.login(email="user1@example.com", password="TestPass123")
        assert token_response.token_type == "bearer"
        assert len(token_response.access_token) > 0

        # Use token to access protected endpoint
        # Note: Connection manager needs to support auth headers
        # For now, test via direct HTTP
        import httpx

        base_url = str(auth_service_manager.url).rstrip("/")
        headers = {"Authorization": f"Bearer {token_response.access_token}"}

        # Test protected endpoint with token
        response = httpx.post(f"{base_url}/protected_data", headers=headers, timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "This is protected data"

    @pytest.mark.asyncio
    async def test_user_injection_in_endpoint(self, auth_service_manager):
        """Test that user info is injected into endpoints that use Depends()."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Login to get token
        token_response = auth_service_manager.login(email="user1@example.com", password="TestPass123")

        # Access endpoint with user injection
        import httpx

        base_url = str(auth_service_manager.url).rstrip("/")
        headers = {"Authorization": f"Bearer {token_response.access_token}"}

        response = httpx.post(f"{base_url}/user_profile", headers=headers, timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user1"
        assert data["email"] == "user1@example.com"
        assert data["name"] == "Test User 1"

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, auth_service_manager):
        """Test that invalid tokens are rejected."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        import httpx

        base_url = str(auth_service_manager.url).rstrip("/")
        headers = {"Authorization": "Bearer invalid_token_12345"}

        response = httpx.post(f"{base_url}/protected_data", headers=headers, timeout=5.0)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, auth_service_manager):
        """Test that missing token is rejected."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        import httpx

        base_url = str(auth_service_manager.url).rstrip("/")

        # No Authorization header
        response = httpx.post(f"{base_url}/protected_data", timeout=5.0)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_public_vs_authenticated_endpoints(self, auth_service_manager):
        """Test that endpoint scopes are correctly enforced."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Check endpoints list
        endpoints = auth_service_manager.endpoints()
        assert isinstance(endpoints, EndpointsOutput)
        assert "public_data" in endpoints.endpoints
        assert "protected_data" in endpoints.endpoints
        assert "user_profile" in endpoints.endpoints
        assert "login" in endpoints.endpoints

    @pytest.mark.asyncio
    async def test_invalid_credentials_rejected(self, auth_service_manager):
        """Test that invalid login credentials are rejected."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Try login with wrong password
        with pytest.raises(Exception):  # Could be HTTPException or requests exception
            auth_service_manager.login(email="user1@example.com", password="WrongPassword")

        # Try login with non-existent user
        with pytest.raises(Exception):
            auth_service_manager.login(email="nonexistent@example.com", password="TestPass123")

    @pytest.mark.asyncio
    async def test_multiple_users_different_tokens(self, auth_service_manager):
        """Test that different users get different tokens and can access their own data."""
        if auth_service_manager is None:
            pytest.skip("Service not available")

        # Login as user1
        token1_response = auth_service_manager.login(email="user1@example.com", password="TestPass123")
        token1 = token1_response.access_token

        # Login as user2
        token2_response = auth_service_manager.login(email="user2@example.com", password="TestPass456")
        token2 = token2_response.access_token

        # Tokens should be different
        assert token1 != token2

        # Both tokens should work for their respective users
        import httpx

        base_url = str(auth_service_manager.url).rstrip("/")

        # User1's token
        response1 = httpx.post(f"{base_url}/user_profile", headers={"Authorization": f"Bearer {token1}"}, timeout=5.0)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["user_id"] == "user1"
        assert data1["email"] == "user1@example.com"

        # User2's token
        response2 = httpx.post(f"{base_url}/user_profile", headers={"Authorization": f"Bearer {token2}"}, timeout=5.0)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["user_id"] == "user2"
        assert data2["email"] == "user2@example.com"
