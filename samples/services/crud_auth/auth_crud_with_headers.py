#!/usr/bin/env python3
"""
Example demonstrating how to use ConnectionManager with authentication headers.

This script shows two approaches:
1. Setting default headers on the connection manager (recommended for most cases)
2. Passing headers per-request (useful for dynamic tokens or different users)
"""

import asyncio

from auth_crud_service import AuthenticatedCRUDService


def sync_example_with_default_headers():
    """Example using default headers - set once, used for all requests."""
    print("=" * 60)
    print("Example 1: Using Default Headers (Recommended)")
    print("=" * 60)

    # Launch the service
    cm = AuthenticatedCRUDService.launch(port=8080, host="localhost", wait_for_launch=True, timeout=30)
    print("✓ Service launched")

    try:
        # First, create a user (public endpoint - no auth needed)
        print("\n1. Creating a user (public endpoint)...")
        user_data = {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "password": "SecurePass123",
            "age": 30,
            "skills": ["Python", "FastAPI"],
        }
        user = cm.create_user(**user_data)
        print(f"   ✓ Created user: {user['name']} (ID: {user['id']})")

        # Login to get a token
        print("\n2. Logging in to get access token...")
        login_response = cm.login(email="alice@example.com", password="SecurePass123")
        token = login_response["access_token"]
        print(f"   ✓ Got access token: {token[:20]}...")

        # Set default headers - all subsequent requests will use this token
        print("\n3. Setting default headers on connection manager...")
        cm.set_default_headers({"Authorization": f"Bearer {token}"})
        print("   ✓ Default headers set")

        # Now all authenticated endpoints will automatically use the token
        print("\n4. Accessing authenticated endpoints (using default headers)...")
        retrieved_user = cm.get_user(user_id=user["id"])
        print(f"   ✓ Retrieved user: {retrieved_user['name']}, email: {retrieved_user['email']}")

        # Update user (authenticated endpoint)
        print("\n5. Updating user (using default headers)...")
        updated_user = cm.update_user(user_id=user["id"], age=31)
        print(f"   ✓ Updated user age to: {updated_user['age']}")

        # Public endpoints still work without headers
        print("\n6. Accessing public endpoints (no headers needed)...")
        all_users = cm.list_users()
        print(f"   ✓ Found {len(all_users)} users")

        print("\n✓ All operations completed successfully!")
        print("\nNote: Default headers are automatically included in all requests.")
        print("      You can override them per-request if needed (see Example 2).")

    finally:
        # Cleanup
        print("\n7. Shutting down service...")
        cm.shutdown(block=False)


def sync_example_with_per_request_headers():
    """Example using per-request headers - useful for dynamic tokens."""
    print("\n" + "=" * 60)
    print("Example 2: Using Per-Request Headers")
    print("=" * 60)

    # Launch the service
    cm = AuthenticatedCRUDService.launch(port=8081, host="localhost", wait_for_launch=True, timeout=30)
    print("✓ Service launched")

    try:
        # Create two users
        print("\n1. Creating users...")
        user1_data = {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "password": "SecurePass456",
            "age": 25,
            "skills": ["JavaScript"],
        }
        user1 = cm.create_user(**user1_data)
        print(f"   ✓ Created user: {user1['name']}")

        user2_data = {
            "name": "Charlie Brown",
            "email": "charlie@example.com",
            "password": "SecurePass789",
            "age": 28,
            "skills": ["Go", "Rust"],
        }
        user2 = cm.create_user(**user2_data)
        print(f"   ✓ Created user: {user2['name']}")

        # Login as user1
        print("\n2. Logging in as user1...")
        login1 = cm.login(email="bob@example.com", password="SecurePass456")
        token1 = login1["access_token"]
        print(f"   ✓ Got token for user1: {token1[:20]}...")

        # Login as user2
        print("\n3. Logging in as user2...")
        login2 = cm.login(email="charlie@example.com", password="SecurePass789")
        token2 = login2["access_token"]
        print(f"   ✓ Got token for user2: {token2[:20]}...")

        # Access user1's data with user1's token (per-request header)
        print("\n4. Accessing user1's data with user1's token...")
        retrieved_user1 = cm.get_user(user_id=user1["id"], headers={"Authorization": f"Bearer {token1}"})
        print(f"   ✓ Retrieved: {retrieved_user1['name']}, email: {retrieved_user1['email']}")

        # Access user2's data with user2's token (per-request header)
        print("\n5. Accessing user2's data with user2's token...")
        retrieved_user2 = cm.get_user(user_id=user2["id"], headers={"Authorization": f"Bearer {token2}"})
        print(f"   ✓ Retrieved: {retrieved_user2['name']}, email: {retrieved_user2['email']}")

        # Update user1 with user1's token
        print("\n6. Updating user1 with user1's token...")
        updated_user1 = cm.update_user(user_id=user1["id"], age=26, headers={"Authorization": f"Bearer {token1}"})
        print(f"   ✓ Updated user1 age to: {updated_user1['age']}")

        print("\n✓ All operations completed successfully!")
        print("\nNote: Per-request headers override default headers if set.")
        print("      This is useful when switching between different users/tokens.")

    finally:
        # Cleanup
        print("\n7. Shutting down service...")
        cm.shutdown(block=False)


async def async_example_with_headers():
    """Example using async methods with headers."""
    print("\n" + "=" * 60)
    print("Example 3: Using Async Methods with Headers")
    print("=" * 60)

    # Launch the service
    cm = AuthenticatedCRUDService.launch(port=8082, host="localhost", wait_for_launch=True, timeout=30)
    print("✓ Service launched")

    try:
        # Create a user
        print("\n1. Creating a user...")
        user_data = {
            "name": "Diana Prince",
            "email": "diana@example.com",
            "password": "SecurePass321",
            "age": 35,
            "skills": ["Python", "Docker", "Kubernetes"],
        }
        user = await cm.acreate_user(**user_data)
        print(f"   ✓ Created user: {user['name']}")

        # Login
        print("\n2. Logging in...")
        login_response = await cm.alogin(email="diana@example.com", password="SecurePass321")
        token = login_response["access_token"]
        print(f"   ✓ Got access token: {token[:20]}...")

        # Set default headers
        print("\n3. Setting default headers...")
        cm.set_default_headers({"Authorization": f"Bearer {token}"})
        print("   ✓ Default headers set")

        # Use async methods with default headers
        print("\n4. Accessing authenticated endpoint (async, using default headers)...")
        retrieved_user = await cm.aget_user(user_id=user["id"])
        print(f"   ✓ Retrieved user: {retrieved_user['name']}")

        # Use async method with per-request header (overrides default)
        print("\n5. Accessing with per-request header (async)...")
        retrieved_user2 = await cm.aget_user(
            user_id=user["id"], headers={"Authorization": f"Bearer {token}", "X-Custom-Header": "custom-value"}
        )
        print(f"   ✓ Retrieved with custom header: {retrieved_user2['name']}")

        print("\n✓ All async operations completed successfully!")

    finally:
        # Cleanup
        print("\n6. Shutting down service...")
        cm.shutdown(block=False)


def example_mixing_default_and_per_request():
    """Example showing how default and per-request headers work together."""
    print("\n" + "=" * 60)
    print("Example 4: Mixing Default and Per-Request Headers")
    print("=" * 60)

    # Launch the service
    cm = AuthenticatedCRUDService.launch(port=8083, host="localhost", wait_for_launch=True, timeout=30)
    print("✓ Service launched")

    try:
        # Create a user
        print("\n1. Creating a user...")
        user = cm.create_user(
            name="Eve Wilson",
            email="eve@example.com",
            password="SecurePass999",
            age=29,
            skills=["TypeScript", "React"],
        )
        print(f"   ✓ Created user: {user['name']}")

        # Login
        print("\n2. Logging in...")
        login_response = cm.login(email="eve@example.com", password="SecurePass999")
        token = login_response["access_token"]
        print("   ✓ Got access token")

        # Set default headers with Authorization and a custom header
        print("\n3. Setting default headers (Authorization + custom header)...")
        cm.set_default_headers(
            {
                "Authorization": f"Bearer {token}",
                "X-Client-Version": "1.0.0",
                "X-Request-Source": "python-client",
            }
        )
        print("   ✓ Default headers set")

        # Request uses default headers
        print("\n4. Request using default headers only...")
        user1 = cm.get_user(user_id=user["id"])
        print(f"   ✓ Retrieved: {user1['name']}")

        # Request with per-request header - merges with defaults, per-request takes precedence
        print("\n5. Request with per-request header (merges with defaults)...")
        user2 = cm.get_user(user_id=user["id"], headers={"X-Custom-Request-ID": "req-12345"})
        print(f"   ✓ Retrieved with merged headers: {user2['name']}")

        # Request with per-request header that overrides default
        print("\n6. Request overriding default Authorization header...")
        # Get a different token (login as same user again)
        login2 = cm.login(email="eve@example.com", password="SecurePass999")
        token2 = login2["access_token"]
        user3 = cm.get_user(user_id=user["id"], headers={"Authorization": f"Bearer {token2}"})
        print(f"   ✓ Retrieved with overridden token: {user3['name']}")

        print("\n✓ Header merging demonstration completed!")
        print("\nNote: Per-request headers merge with defaults, with per-request taking precedence.")

    finally:
        # Cleanup
        print("\n7. Shutting down service...")
        cm.shutdown(block=False)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("ConnectionManager Header Usage Examples")
    print("=" * 60)
    print("\nThis script demonstrates how to use authentication headers")
    print("with ConnectionManager for authenticated endpoints.\n")

    try:
        # Run sync examples
        sync_example_with_default_headers()
        sync_example_with_per_request_headers()
        example_mixing_default_and_per_request()

        # Run async example
        asyncio.run(async_example_with_headers())

        print("\n" + "=" * 60)
        print("All Examples Completed Successfully!")
        print("=" * 60)
        print("\nKey Takeaways:")
        print("1. Use set_default_headers() for most cases - set once, use everywhere")
        print("2. Use per-request headers parameter for dynamic tokens or different users")
        print("3. Per-request headers merge with defaults, with per-request taking precedence")
        print("4. Both sync and async methods support headers")
        print("5. Public endpoints work without headers")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback

        traceback.print_exc()
