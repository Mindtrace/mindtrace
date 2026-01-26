#!/usr/bin/env python3
"""
JWT Token Generator for testing authenticated endpoints.

This script generates JWT tokens for testing the authenticated CRUD service.
"""

import os
import sys
from datetime import UTC, datetime, timedelta

import jwt

# Secret key (must match the one in auth_crud_service.py)
# Use the same default as auth_crud_service.py
JWT_SECRET = os.getenv("JWT_SECRET", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
JWT_ALGORITHM = "HS256"


def generate_token(
    user_id: str = "test_user", email: str = "test@example.com", username: str = "testuser", expires_in_hours: int = 24
) -> str:
    """Generate a JWT token for testing.

    Args:
        user_id: User ID to include in token
        email: Email to include in token
        username: Username to include in token
        expires_in_hours: Token expiration time in hours

    Returns:
        JWT token string
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "username": username,
        "exp": datetime.now(UTC) + timedelta(hours=expires_in_hours),
        "iat": datetime.now(UTC),
    }

    encoded_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_token


if __name__ == "__main__":
    # Generate a test token
    token = generate_token()

    print("=" * 60)
    print("JWT Token Generator")
    print("=" * 60)
    print("\nGenerated Token:")
    print(f"{token}")
    print("\n" + "=" * 60)
    print("Usage:")
    print("=" * 60)
    print("\n1. Use this token in the Authorization header:")
    print(f"   Authorization: Bearer {token}")
    print("\n2. Or use it in curl commands:")
    print(f'   curl -H "Authorization: Bearer {token}" http://localhost:8080/get_user?user_id=...')
    print("\n3. Or use it in Swagger UI:")
    print("   - Click 'Authorize' button at the top")
    print("   - Enter: Bearer <token>")
    print("   - Click 'Authorize'")
    print("\n" + "=" * 60)

    # Also generate with custom values if provided
    if len(sys.argv) > 1:
        custom_user_id = sys.argv[1] if len(sys.argv) > 1 else "test_user"
        custom_email = sys.argv[2] if len(sys.argv) > 2 else "test@example.com"
        custom_username = sys.argv[3] if len(sys.argv) > 3 else "testuser"

        custom_token = generate_token(user_id=custom_user_id, email=custom_email, username=custom_username)
        print(f"\nCustom Token (user_id={custom_user_id}, email={custom_email}):")
        print(f"{custom_token}")
