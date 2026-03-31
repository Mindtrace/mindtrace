#!/usr/bin/env python3
"""
Redis ODM Example

Demonstrates using RedisMindtraceODM with multi-model support.
Redis is natively synchronous but also supports async operations.

Prerequisites:
- Redis running on localhost:6379
"""

import asyncio
from typing import List, Optional

from redis_om import Field

from mindtrace.database import MindtraceRedisDocument, RedisMindtraceODM

# ============================================================================
# Model Definitions
# ============================================================================


class Address(MindtraceRedisDocument):
    """Address model for Redis."""

    street: str = Field(index=True, description="Street address")
    city: str = Field(index=True, description="City")
    state: str = Field(index=True, description="State")
    zip_code: str = Field(description="Zip code")

    class Meta:
        global_key_prefix = "sampleapp"


class User(MindtraceRedisDocument):
    """User model for Redis."""

    name: str = Field(index=True, description="User name")
    email: str = Field(index=True, description="Email address")
    age: int = Field(index=True, ge=0, description="Age")
    skills: List[str] = Field(default_factory=list, description="User skills")
    address_id: Optional[str] = Field(default=None, description="Address ID reference")

    class Meta:
        global_key_prefix = "sampleapp"


# ============================================================================
# Example Functions
# ============================================================================


def demonstrate_sync_operations():
    """Demonstrate synchronous operations (native for Redis)."""
    print("\n" + "=" * 70)
    print("REDIS ODM - SYNCHRONOUS OPERATIONS")
    print("=" * 70)

    # Initialize Redis ODM with multi-model support
    # Auto-initializes on first operation
    db = RedisMindtraceODM(
        models={"user": User, "address": Address},
        redis_url="redis://localhost:6379",
    )

    print(f"✓ Initialized Redis ODM with {len(db._models)} models")

    # CREATE - Insert operations (sync - native)
    print("\n--- CREATE Operations (Sync) ---")

    address_data = {
        "street": "123 Main Street",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94102",
    }
    address = db.address.insert(address_data)
    print(f"✓ Created address: {address.street}, {address.city} (ID: {address.id})")

    user_data = {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "age": 30,
        "skills": ["Python", "Redis"],
        "address_id": address.id,
    }
    user = db.user.insert(user_data)
    print(f"✓ Created user: {user.name} (ID: {user.id})")

    # READ - Retrieve operations
    print("\n--- READ Operations (Sync) ---")

    retrieved_user = db.user.get(user.id)
    print(f"✓ Retrieved user: {retrieved_user.name}, email: {retrieved_user.email}")

    all_users = db.user.all()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations
    print("\n--- UPDATE Operations (Sync) ---")

    retrieved_user.age = 31
    retrieved_user.skills.append("Docker")
    updated_user = db.user.update(retrieved_user)
    print(f"✓ Updated user: {updated_user.name}, age: {updated_user.age}")
    print(f"  Skills: {', '.join(updated_user.skills)}")

    # QUERY - Find operations using Redis OM expressions
    print("\n--- QUERY Operations (Sync) ---")

    # Get raw model for expressions
    UserRedis = db.user.get_raw_model()

    # Find by name
    found = db.user.find(UserRedis.name == "Alice Johnson")
    print(f"✓ Found {len(found)} user(s) with name 'Alice Johnson'")

    # Find by age
    mature_users = db.user.find(UserRedis.age >= 30)
    print(f"✓ Found {len(mature_users)} user(s) with age >= 30")

    # DELETE - Delete operations
    print("\n--- DELETE Operations (Sync) ---")

    db.user.delete(user.id)
    print(f"✓ Deleted user: {user.name}")

    db.address.delete(address.id)
    print(f"✓ Deleted address: {address.street}")

    print("\n✓ Synchronous operations completed!")


async def demonstrate_async_operations():
    """Demonstrate asynchronous operations (wrapper for Redis)."""
    print("\n" + "=" * 70)
    print("REDIS ODM - ASYNCHRONOUS OPERATIONS")
    print("=" * 70)

    db = RedisMindtraceODM(
        models={"user": User, "address": Address},
        redis_url="redis://localhost:6379",
    )

    print("✓ Initialized Redis ODM")

    # CREATE - Insert operations (async - wrapper)
    print("\n--- CREATE Operations (Async) ---")

    address = await db.address.insert_async(
        {"street": "456 Oak Ave", "city": "New York", "state": "NY", "zip_code": "10001"}
    )
    print(f"✓ Created address: {address.street}, {address.city}")

    user = await db.user.insert_async(
        {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 25,
            "skills": ["JavaScript", "Node.js"],
            "address_id": address.id,
        }
    )
    print(f"✓ Created user: {user.name}")

    # READ - Retrieve operations (async)
    print("\n--- READ Operations (Async) ---")

    retrieved = await db.user.get_async(user.id)
    print(f"✓ Retrieved user: {retrieved.name}")

    all_users = await db.user.all_async()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations (async)
    print("\n--- UPDATE Operations (Async) ---")

    retrieved.age = 26
    retrieved.skills.append("TypeScript")
    updated = await db.user.update_async(retrieved)
    print(f"✓ Updated user: {updated.name}, age: {updated.age}")

    # QUERY - Find operations (async)
    print("\n--- QUERY Operations (Async) ---")

    UserRedis = db.user.get_raw_model()
    found = await db.user.find_async(UserRedis.age >= 25)
    print(f"✓ Found {len(found)} user(s) with age >= 25")

    # DELETE - Delete operations (async)
    print("\n--- DELETE Operations (Async) ---")

    await db.user.delete_async(user.id)
    await db.address.delete_async(address.id)
    print("✓ Cleaned up")

    print("\n✓ Asynchronous operations completed!")


async def main():
    """Run all Redis ODM demonstrations."""
    print("\n" + "=" * 70)
    print("REDIS ODM EXAMPLE")
    print("=" * 70)
    print("\nThis example demonstrates:")
    print("  • Multi-model support")
    print("  • Synchronous operations (native)")
    print("  • Asynchronous operations (wrapper)")
    print("  • Redis OM query expressions")
    print("  • CRUD operations")

    try:
        # Demonstrate sync operations
        demonstrate_sync_operations()

        # Demonstrate async operations
        await demonstrate_async_operations()

        print("\n" + "=" * 70)
        print("ALL REDIS ODM DEMONSTRATIONS COMPLETED!")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
