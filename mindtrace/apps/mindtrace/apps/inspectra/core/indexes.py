"""MongoDB index management for Inspectra."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_indexes(db: "AsyncIOMotorDatabase") -> None:
    """
    Create required indexes on MongoDB collections.

    Call this during application startup to ensure optimal query performance.
    """
    # Users collection
    await db.users.create_index("username", unique=True)
    await db.users.create_index("is_active")
    await db.users.create_index("plant_id")
    await db.users.create_index("role_id")

    # Roles collection
    await db.roles.create_index("name", unique=True)

    # Plants collection
    await db.plants.create_index("code", unique=True)
    await db.plants.create_index("is_active")

    # Lines collection
    await db.lines.create_index("plant_id")
    await db.lines.create_index([("plant_id", 1), ("name", 1)])

    # Password policies collection
    await db.password_policies.create_index([("is_default", 1), ("is_active", 1)])
    await db.password_policies.create_index("is_active")

    # Policy rules collection
    await db.policy_rules.create_index("policy_id")

    # Licenses collection
    await db.licenses.create_index("is_active")
    await db.licenses.create_index("license_key", unique=True)
