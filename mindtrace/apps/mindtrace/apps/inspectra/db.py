"""Database module for Inspectra using mindtrace.database.MongoMindtraceODM.

This module provides a global ODM instance with multi-model support for all
Inspectra document types. The ODM handles connection pooling, index creation,
and provides a type-safe interface for database operations.
"""

from typing import Optional

from mindtrace.database import MongoMindtraceODM

from mindtrace.apps.inspectra.core import get_inspectra_config
from mindtrace.apps.inspectra.models.documents import (
    LicenseDocument,
    LineDocument,
    PasswordPolicyDocument,
    PlantDocument,
    PolicyRuleDocument,
    RoleDocument,
    UserDocument,
)

_db: Optional[MongoMindtraceODM] = None


def get_db() -> MongoMindtraceODM:
    """
    Get the global MongoMindtraceODM instance.

    Creates the instance on first call but does NOT initialize Beanie.
    Initialization happens via `initialize_db()` during application startup.

    Returns:
        MongoMindtraceODM: The global ODM instance with multi-model support.
            Access collections via: db.user, db.role, db.plant, db.line, etc.
    """
    global _db
    if _db is None:
        cfg = get_inspectra_config().INSPECTRA
        _db = MongoMindtraceODM(
            models={
                "user": UserDocument,
                "role": RoleDocument,
                "plant": PlantDocument,
                "line": LineDocument,
                "password_policy": PasswordPolicyDocument,
                "policy_rule": PolicyRuleDocument,
                "license": LicenseDocument,
            },
            db_uri=cfg.MONGO_URI,
            db_name=cfg.MONGO_DB,
        )
    return _db


async def initialize_db() -> None:
    """
    Explicitly initialize the database connection and Beanie ODM.

    Should be called during application startup for predictable initialization.
    This initializes the Motor client, connects to MongoDB, and creates indexes
    defined in document Settings.
    """
    db = get_db()
    await db.initialize()


async def close_db() -> None:
    """
    Close the database connection.

    Should be called during application shutdown for clean resource cleanup.
    """
    global _db
    if _db is not None:
        _db.client.close()
        _db = None


def reset_db() -> None:
    """
    Reset the global ODM instance.

    Useful in tests to ensure a fresh database instance.
    Does NOT close the connection - use close_db() first if needed.
    """
    global _db
    _db = None
