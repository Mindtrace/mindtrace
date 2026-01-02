#!/usr/bin/env python3
"""
MongoDB ODM Example

Demonstrates using MongoMindtraceODM with multi-model support.
MongoDB is natively asynchronous but also supports sync operations.

Prerequisites:
- MongoDB running on localhost:27017
"""

import asyncio
from typing import List, Optional

from pydantic import Field

from mindtrace.database import Link, MindtraceDocument, MongoMindtraceODM


# ============================================================================
# Model Definitions
# ============================================================================

class Address(MindtraceDocument):
    """Address model for MongoDB."""

    street: str = Field(description="Street address")
    city: str = Field(description="City")
    state: str = Field(description="State")
    zip_code: str = Field(description="Zip code")

    class Settings:
        name = "addresses"
        use_cache = False


class User(MindtraceDocument):
    """User model for MongoDB with linked address."""

    name: str = Field(description="User name")
    email: str = Field(description="Email address")
    age: int = Field(ge=0, description="Age")
    skills: List[str] = Field(default_factory=list, description="User skills")
    address: Optional[Link[Address]] = Field(default=None, description="Linked address")

    class Settings:
        name = "users"
        use_cache = False


# ============================================================================
# Example Functions
# ============================================================================

async def demonstrate_async_operations():
    """Demonstrate asynchronous operations (native for MongoDB)."""
    print("\n" + "=" * 70)
    print("MONGODB ODM - ASYNCHRONOUS OPERATIONS")
    print("=" * 70)

    # Initialize MongoDB ODM with multi-model support
    # Auto-initializes on first operation
    db = MongoMindtraceODM(
        models={"user": User, "address": Address},
        db_uri="mongodb://localhost:27017",
        db_name="sampleapp",
        allow_index_dropping=True,
    )

    print(f"✓ Initialized MongoDB ODM with {len(db._models)} models")

    # CREATE - Insert operations (async - native)
    print("\n--- CREATE Operations (Async) ---")

    address_data = {
        "street": "123 Main Street",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94102",
    }
    address = await db.address.insert(address_data)
    print(f"✓ Created address: {address.street}, {address.city} (ID: {address.id})")

    # Get the MongoDB document for linking
    address_mongo = await Address.get(address.id)

    # Create user with linked address
    user_data = {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "age": 30,
        "skills": ["Python", "MongoDB"],
        "address": address_mongo,  # Link to address document
    }
    user = await db.user.insert(user_data)
    print(f"✓ Created user: {user.name} (ID: {user.id})")

    # READ - Retrieve operations
    print("\n--- READ Operations (Async) ---")

    # Get user with linked address
    retrieved_user = await db.user.get(user.id, fetch_links=True)
    print(f"✓ Retrieved user: {retrieved_user.name}, email: {retrieved_user.email}")
    if retrieved_user.address:
        print(
            f"  Address: {retrieved_user.address.street}, "
            f"{retrieved_user.address.city}, {retrieved_user.address.state}"
        )

    all_users = await db.user.all()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations
    print("\n--- UPDATE Operations (Async) ---")

    retrieved_user.age = 31
    retrieved_user.skills.append("Docker")
    updated_user = await db.user.update(retrieved_user)
    print(f"✓ Updated user: {updated_user.name}, age: {updated_user.age}")
    print(f"  Skills: {', '.join(updated_user.skills)}")

    # QUERY - Find operations using Beanie expressions
    print("\n--- QUERY Operations (Async) ---")

    # Find by name with linked documents
    found = await db.user.find(User.name == "Alice Johnson", fetch_links=True)
    print(f"✓ Found {len(found)} user(s) with name 'Alice Johnson'")
    for u in found:
        addr_info = f", {u.address.street}, {u.address.city}" if u.address else ""
        print(f"  - {u.name}, email: {u.email}{addr_info}")

    # Find by age
    mature_users = await db.user.find(User.age >= 30, fetch_links=True)
    print(f"✓ Found {len(mature_users)} user(s) with age >= 30")

    # MongoDB-style queries
    users_by_skill = await db.user.find({"skills": "Python"}, fetch_links=True)
    print(f"✓ Found {len(users_by_skill)} user(s) with Python skill")

    # DELETE - Delete operations
    print("\n--- DELETE Operations (Async) ---")

    await db.user.delete(user.id)
    print(f"✓ Deleted user: {user.name}")

    await db.address.delete(address.id)
    print(f"✓ Deleted address: {address.street}")

    print("\n✓ Asynchronous operations completed!")


def demonstrate_sync_operations():
    """Demonstrate synchronous operations (wrapper for MongoDB)."""
    print("\n" + "=" * 70)
    print("MONGODB ODM - SYNCHRONOUS OPERATIONS")
    print("=" * 70)

    db = MongoMindtraceODM(
        models={"user": User, "address": Address},
        db_uri="mongodb://localhost:27017",
        db_name="sampleapp",
    )

    print("✓ Initialized MongoDB ODM")

    # CREATE - Insert operations (sync - wrapper)
    print("\n--- CREATE Operations (Sync) ---")

    address = db.address.insert_sync(
        {"street": "456 Oak Ave", "city": "New York", "state": "NY", "zip_code": "10001"}
    )
    print(f"✓ Created address: {address.street}, {address.city}")

    # For linking, we need to get the MongoDB document
    # Note: In sync mode, linking is more complex, so we'll use address_id pattern
    user = db.user.insert_sync(
        {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 25,
            "skills": ["JavaScript", "Node.js"],
        }
    )
    print(f"✓ Created user: {user.name}")

    # READ - Retrieve operations (sync)
    print("\n--- READ Operations (Sync) ---")

    retrieved = db.user.get_sync(user.id)
    print(f"✓ Retrieved user: {retrieved.name}")

    all_users = db.user.all_sync()
    print(f"✓ Total users: {len(all_users)}")

    # UPDATE - Update operations (sync)
    print("\n--- UPDATE Operations (Sync) ---")

    retrieved.age = 26
    retrieved.skills.append("TypeScript")
    updated = db.user.update_sync(retrieved)
    print(f"✓ Updated user: {updated.name}, age: {updated.age}")

    # DELETE - Delete operations (sync)
    print("\n--- DELETE Operations (Sync) ---")

    db.user.delete_sync(user.id)
    db.address.delete_sync(address.id)
    print("✓ Cleaned up")

    print("\n✓ Synchronous operations completed!")


async def main():
    """Run all MongoDB ODM demonstrations."""
    print("\n" + "=" * 70)
    print("MONGODB ODM EXAMPLE")
    print("=" * 70)
    print("\nThis example demonstrates:")
    print("  • Multi-model support")
    print("  • Asynchronous operations (native)")
    print("  • Synchronous operations (wrapper)")
    print("  • Linked documents with fetch_links")
    print("  • Beanie query expressions")
    print("  • MongoDB-style queries")
    print("  • CRUD operations")

    try:
        # Demonstrate async operations (recommended)
        await demonstrate_async_operations()

        # Demonstrate sync operations
        demonstrate_sync_operations()

        print("\n" + "=" * 70)
        print("ALL MONGODB ODM DEMONSTRATIONS COMPLETED!")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

