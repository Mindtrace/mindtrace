#!/usr/bin/env python3
"""
Unified ODM Example

Demonstrates using UnifiedMindtraceODM with multi-model support.
Works with both MongoDB and Redis backends using a unified interface.

Prerequisites:
- MongoDB running on localhost:27017
- Redis running on localhost:6379
"""

import asyncio
from typing import List, Optional

from pydantic import Field

from mindtrace.database import (
    BackendType,
    UnifiedMindtraceDocument,
    UnifiedMindtraceODM,
)


# ============================================================================
# Model Definitions
# ============================================================================

class Address(UnifiedMindtraceDocument):
    """Address model - works with both MongoDB and Redis."""

    street: str = Field(description="Street address", min_length=1)
    city: str = Field(description="City name", min_length=1)
    state: str = Field(description="State abbreviation", min_length=2, max_length=2)
    zip_code: str = Field(description="ZIP code", pattern=r"^\d{5}(-\d{4})?$")

    class Meta:
        collection_name = "addresses"
        global_key_prefix = "sampleapp"
        indexed_fields = ["city", "state", "zip_code"]


class User(UnifiedMindtraceDocument):
    """User model - works with both MongoDB and Redis."""

    name: str = Field(description="User's full name", min_length=1)
    email: str = Field(description="Email address", pattern=r"^[^@]+@[^@]+\.[^@]+$")
    age: int = Field(description="User's age", ge=0, le=150)
    skills: List[str] = Field(default_factory=list, description="List of skills")
    address_id: Optional[str] = Field(default=None, description="Reference to address document")
    is_active: bool = Field(default=True, description="Account status")

    class Meta:
        collection_name = "users"
        global_key_prefix = "sampleapp"
        indexed_fields = ["email", "name", "age", "is_active"]
        unique_fields = ["email"]


# ============================================================================
# Example Functions
# ============================================================================

async def demonstrate_mongo_backend():
    """Demonstrate unified ODM with MongoDB backend."""
    print("\n" + "=" * 70)
    print("UNIFIED ODM - MONGODB BACKEND")
    print("=" * 70)

    # Initialize unified ODM with MongoDB as preferred backend
    db = UnifiedMindtraceODM(
        unified_models={"user": User, "address": Address},
        mongo_db_uri="mongodb://localhost:27017",
        mongo_db_name="sampleapp",
        preferred_backend=BackendType.MONGO,
        allow_index_dropping=True,
    )

    print(f"✓ Initialized Unified ODM with MongoDB backend")
    print(f"✓ Current backend: {db.get_current_backend_type()}")
    print(f"✓ Has MongoDB: {db.has_mongo_backend()}")
    print(f"✓ Has Redis: {db.has_redis_backend()}")

    # CREATE - Insert operations
    print("\n--- CREATE Operations ---")

    address_data = {
        "street": "123 Main Street",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94102",
    }
    address = await db.address.insert_async(address_data)
    print(f"✓ Created address: {address.street}, {address.city} (ID: {address.id})")

    user_data = {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "age": 30,
        "skills": ["Python", "MongoDB"],
        "address_id": address.id,
    }
    user = await db.user.insert_async(user_data)
    print(f"✓ Created user: {user.name} (ID: {user.id})")

    # READ - Retrieve operations
    print("\n--- READ Operations ---")

    retrieved_user = await db.user.get_async(user.id)
    print(f"✓ Retrieved user: {retrieved_user.name}, email: {retrieved_user.email}")

    all_users = await db.user.all_async()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations
    print("\n--- UPDATE Operations ---")

    retrieved_user.age = 31
    retrieved_user.skills.append("Redis")
    updated_user = await db.user.update_async(retrieved_user)
    print(f"✓ Updated user: {updated_user.name}, age: {updated_user.age}")

    # QUERY - Find operations (MongoDB-style)
    print("\n--- QUERY Operations (MongoDB-style) ---")

    mature_users = await db.user.find_async({"age": {"$gte": 30}})
    print(f"✓ Found {len(mature_users)} user(s) with age >= 30")

    users_by_skill = await db.user.find_async({"skills": "Python"})
    print(f"✓ Found {len(users_by_skill)} user(s) with Python skill")

    # DELETE - Delete operations
    print("\n--- DELETE Operations ---")

    await db.user.delete_async(user.id)
    await db.address.delete_async(address.id)
    print("✓ Cleaned up")

    print("\n✓ MongoDB backend demonstration completed!")


async def demonstrate_redis_backend():
    """Demonstrate unified ODM with Redis backend."""
    print("\n" + "=" * 70)
    print("UNIFIED ODM - REDIS BACKEND")
    print("=" * 70)

    # Initialize unified ODM with Redis as preferred backend
    db = UnifiedMindtraceODM(
        unified_models={"user": User, "address": Address},
        redis_url="redis://localhost:6379",
        preferred_backend=BackendType.REDIS,
    )

    print(f"✓ Initialized Unified ODM with Redis backend")
    print(f"✓ Current backend: {db.get_current_backend_type()}")

    # CREATE - Insert operations (sync - native for Redis)
    print("\n--- CREATE Operations (Sync) ---")

    address = db.address.insert(
        {"street": "456 Oak Ave", "city": "New York", "state": "NY", "zip_code": "10001"}
    )
    print(f"✓ Created address: {address.street}, {address.city} (ID: {address.id})")

    user = db.user.insert(
        {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 25,
            "skills": ["JavaScript", "Redis"],
            "address_id": address.id,
        }
    )
    print(f"✓ Created user: {user.name} (ID: {user.id})")

    # READ - Retrieve operations
    print("\n--- READ Operations ---")

    retrieved_user = db.user.get(user.id)
    print(f"✓ Retrieved user: {retrieved_user.name}, email: {retrieved_user.email}")

    all_users = db.user.all()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations
    print("\n--- UPDATE Operations ---")

    retrieved_user.age = 26
    retrieved_user.skills.append("Node.js")
    updated_user = db.user.update(retrieved_user)
    print(f"✓ Updated user: {updated_user.name}, age: {updated_user.age}")

    # QUERY - Find operations (Redis OM expressions)
    print("\n--- QUERY Operations (Redis OM expressions) ---")

    # Get raw Redis model for expressions
    UserRedis = db.user.get_raw_model()

    found = db.user.find(UserRedis.name == "Bob Smith")
    print(f"✓ Found {len(found)} user(s) with name 'Bob Smith'")

    mature_users = db.user.find(UserRedis.age >= 25)
    print(f"✓ Found {len(mature_users)} user(s) with age >= 25")

    # DELETE - Delete operations
    print("\n--- DELETE Operations ---")

    db.user.delete(user.id)
    db.address.delete(address.id)
    print("✓ Cleaned up")

    print("\n✓ Redis backend demonstration completed!")

async def main():
    """Run all unified ODM demonstrations."""
    print("\n" + "=" * 70)
    print("UNIFIED ODM EXAMPLE")
    print("=" * 70)
    print("\nThis example demonstrates:")
    print("  • Multi-model support")
    print("  • MongoDB backend operations")
    print("  • Redis backend operations")
    print("  • Unified interface across backends")
    print("  • CRUD operations")

    try:
        # Demonstrate MongoDB backend
        await demonstrate_mongo_backend()

        # Demonstrate Redis backend
        await demonstrate_redis_backend()

        print("\n" + "=" * 70)
        print("ALL UNIFIED ODM DEMONSTRATIONS COMPLETED!")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

