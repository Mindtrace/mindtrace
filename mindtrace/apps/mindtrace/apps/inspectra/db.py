"""
Database layer for Inspectra using Mindtrace Mongo ODM.

Provides a global MongoMindtraceODM instance configured with User and Organization
models for auth and RBAC. Beanie is initialized on first use.
"""

from typing import Optional

from mindtrace.apps.inspectra.core import get_inspectra_config
from mindtrace.apps.inspectra.models import Organization, User
from mindtrace.database import MongoMindtraceODM

_odm: Optional[MongoMindtraceODM] = None


def get_odm() -> MongoMindtraceODM:
    """Get or create the global MongoMindtraceODM instance.

    Uses User and Organization models only. The ODM is created on first call
    from Inspectra config (MONGO_URI, MONGO_DB_NAME). Beanie document models
    are initialized on first async operation.

    Returns:
        MongoMindtraceODM: The shared ODM instance (multi-model: user, organization).
    """
    global _odm
    if _odm is None:
        cfg = get_inspectra_config().INSPECTRA
        _odm = MongoMindtraceODM(
            models={"user": User, "organization": Organization},
            db_uri=cfg.MONGO_URI,
            db_name=cfg.MONGO_DB_NAME,
            allow_index_dropping=False,
        )
    return _odm


async def init_db() -> None:
    """Initialize the ODM so it is ready for requests.

    Calls initialize() on the global MongoMindtraceODM. Idempotent; safe to
    call multiple times. Should be invoked at application startup.
    """
    odm = get_odm()
    await odm.initialize()


def close_db() -> None:
    """Close the ODM client if it exists.

    Cleans up the Motor client and clears the global ODM reference. Intended
    for use on application shutdown.
    """
    global _odm
    if _odm is not None and hasattr(_odm, "client"):
        _odm.client.close()
        _odm = None
