#!/usr/bin/env python3
"""
Authenticated CRUD Service Demo - Demonstrates how to use the authenticated CRUD service.

This script shows:
1. Generating JWT tokens
2. Creating users (public)
3. Reading users (authenticated)
4. Updating users (authenticated)
5. Deleting users (authenticated)
6. Listing all users (public)
7. Searching users (public)
8. Both sync and async usage
"""

import asyncio
import os
import traceback
from datetime import datetime, timedelta

import httpx
import jwt
from auth_crud_service import JWT_ALGORITHM, JWT_SECRET, AuthenticatedCRUDService
from fastapi import HTTPException


def generate_test_token(user_id: str = "demo_user", email: str = "demo@example.com", username: str = "demo"):
    """Generate a test JWT token."""

    payload = {
        "user_id": user_id,
        "email": email,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def sync_crud_example():
    """Demonstrate synchronous authenticated CRUD operations."""
    print("=" * 60)
    print("SYNCHRONOUS AUTHENTICATED CRUD OPERATIONS DEMO")
    print("=" * 60)

    # Generate a test token
    token = generate_test_token()
    print(f"\nGenerated test token: {token[:50]}...")

    # Launch the service
    print("\n1. Launching Authenticated CRUD Service...")
    cm = AuthenticatedCRUDService.launch(
        port=8081,  # Use different port to avoid conflicts
        host="localhost",
        wait_for_launch=True,
        timeout=30,
        mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        mongo_db_name=os.getenv("MONGO_DB_NAME", "auth_crud_demo"),
    )
    print(f"   Service running at: {cm.url}")

    # Create HTTP client with authentication
    client = httpx.Client(base_url=str(cm.url).rstrip("/"), timeout=60.0)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # CREATE - Add some users (authenticated)
        print("\n2. Creating users (authenticated endpoint)...")

        user1_data = {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "age": 30,
            "skills": ["Python", "FastAPI", "MongoDB"],
        }
        response = client.post("/create_user", json=user1_data, headers=headers)
        if response.status_code == 200:
            user1 = response.json()
            print(f"   Created: {user1['name']} (ID: {user1['id']})")
        else:
            print(f"   Error: {response.status_code} - {response.text}")
            return

        user2_data = {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 25,
            "skills": ["JavaScript", "Node.js"],
        }
        response = client.post("/create_user", json=user2_data, headers=headers)
        if response.status_code == 200:
            user2 = response.json()
            print(f"   Created: {user2['name']} (ID: {user2['id']})")
        else:
            print(f"   Error: {response.status_code} - {response.text}")

        # READ - Get user (authenticated)
        print("\n3. Reading user (authenticated endpoint)...")
        response = client.get(f"/get_user?user_id={user1['id']}", headers=headers)
        if response.status_code == 200:
            retrieved = response.json()
            name = retrieved["name"]
            email = retrieved["email"]
            age = retrieved["age"]
            print(f"   Retrieved: {name}, email: {email}, age: {age}")
            print(f"   Skills: {', '.join(retrieved['skills'])}")

        # LIST - List all users (public endpoint, no auth needed)
        print("\n4. Listing all users (public endpoint)...")
        response = client.get("/list_users")
        if response.status_code == 200:
            result = response.json()
            print(f"   Total users: {result['total']}")
            for user in result["users"]:
                print(f"   - {user['name']} ({user['email']})")

        # SEARCH - Search users (public endpoint)
        print("\n5. Searching users (public endpoint)...")
        response = client.get("/search_users?skill=Python&limit=10")
        if response.status_code == 200:
            result = response.json()
            print(f"   Found {result['total']} user(s) with Python skill:")
            for user in result["users"]:
                print(f"   - {user['name']} ({user['email']})")

        # UPDATE - Update user (authenticated)
        print("\n6. Updating user (authenticated endpoint)...")
        update_data = {
            "user_id": user1["id"],
            "age": 31,
            "skills": ["Python", "FastAPI", "MongoDB", "Docker"],
        }
        response = client.put("/update_user", json=update_data, headers=headers)
        if response.status_code == 200:
            updated = response.json()
            print(f"   Updated: {updated['name']}, age: {updated['age']}")
            print(f"   Skills: {', '.join(updated['skills'])}")

        # DELETE - Delete user (authenticated)
        print("\n7. Deleting user (authenticated endpoint)...")
        response = client.delete(f"/delete_user?user_id={user2['id']}", headers=headers)
        if response.status_code == 200:
            deleted = response.json()
            print(f"   Deleted: {deleted['name']}")

        # Verify deletion
        print("\n8. Verifying deletion...")
        response = client.get("/list_users")
        if response.status_code == 200:
            result = response.json()
            print(f"   Remaining users: {result['total']}")

        print("\n" + "=" * 60)
        print("SYNCHRONOUS DEMO COMPLETED!")
        print("=" * 60)

    except (
        httpx.HTTPError,
        httpx.RequestError,
        HTTPException,
        RuntimeError,
        ConnectionError,
        TimeoutError,
    ) as e:
        print(f"\nError: {e}")
        traceback.print_exc()
    finally:
        client.close()


async def async_crud_example():
    """Demonstrate asynchronous authenticated CRUD operations."""
    print("\n" + "=" * 60)
    print("ASYNCHRONOUS AUTHENTICATED CRUD OPERATIONS DEMO")
    print("=" * 60)

    # Generate a test token
    token = generate_test_token()
    print(f"\nGenerated test token: {token[:50]}...")

    # Launch the service
    print("\n1. Launching Authenticated CRUD Service...")
    cm = AuthenticatedCRUDService.launch(
        port=8082,  # Use different port
        host="localhost",
        wait_for_launch=True,
        timeout=30,
        mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        mongo_db_name=os.getenv("MONGO_DB_NAME", "auth_crud_demo_async"),
    )
    print(f"   Service running at: {cm.url}")

    # Create async HTTP client with authentication
    async with httpx.AsyncClient(base_url=str(cm.url).rstrip("/"), timeout=60.0) as client:
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # CREATE - Add users (authenticated)
            print("\n2. Creating users (authenticated endpoint)...")

            user1_data = {
                "name": "Charlie Brown",
                "email": "charlie@example.com",
                "age": 28,
                "skills": ["Go", "Kubernetes"],
            }
            response = await client.post("/create_user", json=user1_data, headers=headers)
            if response.status_code == 200:
                user1 = response.json()
                print(f"   Created: {user1['name']} (ID: {user1['id']})")

            # READ - Get user (authenticated)
            print("\n3. Reading user (authenticated endpoint)...")
            response = await client.get(f"/get_user?user_id={user1['id']}", headers=headers)
            if response.status_code == 200:
                retrieved = response.json()
                print(f"   Retrieved: {retrieved['name']}, email: {retrieved['email']}")

            # LIST - List all users (public)
            print("\n4. Listing all users (public endpoint)...")
            response = await client.get("/list_users")
            if response.status_code == 200:
                result = response.json()
                print(f"   Total users: {result['total']}")

            print("\n" + "=" * 60)
            print("ASYNCHRONOUS DEMO COMPLETED!")
            print("=" * 60)

        except (
            httpx.HTTPError,
            httpx.RequestError,
            HTTPException,
            RuntimeError,
            ConnectionError,
            TimeoutError,
        ) as e:
            print(f"\nError: {e}")
            traceback.print_exc()


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("AUTHENTICATED CRUD SERVICE DEMO")
    print("=" * 60)
    print("\nThis demo demonstrates:")
    print("  • JWT token generation")
    print("  • Authenticated CRUD operations")
    print("  • Public endpoints (no auth required)")
    print("  • MongoDB persistence")
    print("  • Both sync and async usage")
    print("\nPrerequisites:")
    print("  • MongoDB running on localhost:27017")
    print("  • Service dependencies installed")

    try:
        # Run sync demo
        sync_crud_example()

        # Run async demo
        asyncio.run(async_crud_example())

        print("\n" + "=" * 60)
        print("ALL DEMOS COMPLETED!")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except (
        httpx.HTTPError,
        httpx.RequestError,
        HTTPException,
        RuntimeError,
        ConnectionError,
        TimeoutError,
    ) as e:
        print(f"\n\nError running demo: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
