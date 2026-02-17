"""Seed module for initializing default data in Inspectra.

This module creates default roles and a super admin user on first startup.
It's idempotent - running it multiple times won't duplicate data.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.core.security import hash_password_async
from mindtrace.apps.inspectra.models.documents import (
    RoleDocument,
    UserDocument,
    PasswordPolicyDocument,
    PolicyRuleDocument,
)

logger = logging.getLogger(__name__)

# Default super admin credentials (can be overridden via environment variables)
DEFAULT_ADMIN_EMAIL = os.getenv("INSPECTRA__ADMIN_EMAIL", "admin@inspectra.local")
DEFAULT_ADMIN_PASSWORD = os.getenv("INSPECTRA__ADMIN_PASSWORD", "Admin123!@#abc")


async def seed_roles() -> Optional[str]:
    """
    Create default roles if they don't exist.

    Returns:
        The admin role ID if created/found, None on error.
    """
    db = get_db()

    # Define default roles
    default_roles = [
        {
            "name": "admin",
            "description": "Administrator with full access",
            "permissions": [
                "users:read", "users:write", "users:delete",
                "roles:read", "roles:write",
                "plants:read", "plants:write", "plants:delete",
                "lines:read", "lines:write", "lines:delete",
                "policies:read", "policies:write", "policies:delete",
                "license:read", "license:write",
            ],
        },
        {
            "name": "user",
            "description": "Standard user with limited access",
            "permissions": ["plants:read", "lines:read"],
        },
    ]

    admin_role_id = None

    for role_data in default_roles:
        # Check if role exists
        existing = await db.role.sync({"name": role_data["name"]})

        if existing:
            logger.info(f"Role '{role_data['name']}' already exists")
            if role_data["name"] == "admin":
                admin_role_id = str(existing.id)
        else:
            # Create the role
            role = RoleDocument(**role_data)
            await db.role.insert(role)
            logger.info(f"Created role: {role_data['name']}")
            if role_data["name"] == "admin":
                admin_role_id = str(role.id)

    return admin_role_id


async def seed_admin_user(admin_role_id: str) -> None:
    """
    Create default super admin user if it doesn't exist.

    Args:
        admin_role_id: The ID of the admin role to assign.
    """
    db = get_db()

    # Check if admin user exists
    existing = await db.user.find_sync({"email": DEFAULT_ADMIN_EMAIL})

    if existing:
        logger.info(f"Admin user '{DEFAULT_ADMIN_EMAIL}' already exists")
        return

    # Hash the password
    password_hash = await hash_password_async(DEFAULT_ADMIN_PASSWORD)

    # Create admin user
    admin_user = UserDocument(
        email=DEFAULT_ADMIN_EMAIL,
        password_hash=password_hash,
        role_id=admin_role_id,
        is_active=True,
        password_changed_at=datetime.utcnow(),
    )

    await db.user.insert(admin_user)
    logger.info(f"Created admin user: {DEFAULT_ADMIN_EMAIL}")
    logger.info(f"Default password: {DEFAULT_ADMIN_PASSWORD} (change this in production!)")


async def seed_default_password_policy() -> None:
    """Create a default password policy with rules if none exists."""
    db = get_db()

    # Check if any default policy exists
    existing = await db.password_policy.find_sync({"is_default": True})

    if existing:
        logger.info("Default password policy already exists")
        return

    # Create the default policy
    policy = PasswordPolicyDocument(
        name="Default Policy",
        description="Password must be 12+ characters with uppercase, lowercase, and numbers. Expires every 90 days.",
        is_active=True,
        is_default=True,
    )

    await db.password_policy.insert(policy)
    policy_id = str(policy.id)
    logger.info("Created default password policy")

    # Define password policy rules
    rules = [
        {
            "policy_id": policy_id,
            "rule_type": "min_length",
            "value": 12,
            "message": "Password must be at least 12 characters",
            "is_active": True,
            "order": 1,
        },
        {
            "policy_id": policy_id,
            "rule_type": "require_uppercase",
            "value": True,
            "message": "Password must contain at least one uppercase letter",
            "is_active": True,
            "order": 2,
        },
        {
            "policy_id": policy_id,
            "rule_type": "require_lowercase",
            "value": True,
            "message": "Password must contain at least one lowercase letter",
            "is_active": True,
            "order": 3,
        },
        {
            "policy_id": policy_id,
            "rule_type": "require_digit",
            "value": True,
            "message": "Password must contain at least one number",
            "is_active": True,
            "order": 4,
        },
    ]

    # Insert all rules
    for rule_data in rules:
        rule = PolicyRuleDocument(**rule_data)
        await db.policy_rule.insert(rule)
        logger.info(f"Created password policy rule: {rule_data['rule_type']}")


async def run_seed() -> None:
    """
    Run all seed operations.

    This function is idempotent - it checks for existing data before creating.
    """
    logger.info("Starting database seeding...")

    try:
        # Seed roles first (admin user needs the admin role ID)
        admin_role_id = await seed_roles()

        # Seed admin user
        if admin_role_id:
            await seed_admin_user(admin_role_id)
        else:
            logger.warning("Could not create admin user - admin role not found")

        # Seed default password policy
        await seed_default_password_policy()

        logger.info("Database seeding completed successfully")

    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        raise