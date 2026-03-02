"""
User model for Inspectra.

MongoDB document representing a system user. Extends MindtraceDocument with
organization link, email (and normalized email_norm for lookup), role, name,
password hash, and optional plant/line links. Unique index on email_norm.
"""

from datetime import datetime, timezone
from typing import List

from beanie import Delete, Insert, Link, Replace, SaveChanges, after_event, before_event
from pydantic import EmailStr, Field
from pymongo import ASCENDING, IndexModel
from typing_extensions import Any, Dict

from mindtrace.apps.inspectra.models.enums import UserRole, UserStatus
from mindtrace.apps.inspectra.models.line import Line
from mindtrace.apps.inspectra.models.organization import Organization
from mindtrace.apps.inspectra.models.plant import Plant
from mindtrace.database import MindtraceDocument


class User(MindtraceDocument):
    """User document for auth and RBAC.

    Attributes:
        organization: Link to the Organization the user belongs to.
        email: User email (validated as EmailStr).
        email_norm: Lowercase email for case-insensitive lookup; set in before_save.
        role: User role (e.g. super_admin, admin, user).
        first_name: Given name.
        last_name: Family name.
        pw_hash: Hashed password (e.g. PBKDF2).
        status: UserStatus (active or inactive).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    organization: Link[Organization]
    email: EmailStr
    email_norm: str = ""
    role: UserRole
    first_name: str
    last_name: str
    pw_hash: str
    plants: List[Link[Plant]] = Field(default_factory=list)
    lines: List[Link[Line]] = Field(default_factory=list)
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    async def before_save(self):
        """Normalize email to lowercase and set email_norm before saving."""
        self.email_norm = self.email.casefold()

    class Settings:
        """Beanie collection and index settings for User."""

        name = "users"
        indexes = [
            IndexModel([("email_norm", ASCENDING)], unique=True),
        ]

    @before_event(Insert)
    async def before_insert(self):
        """Set email_norm, created_at and updated_at before insert."""
        self.email_norm = self.email.casefold()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @before_event(Replace)
    async def before_replace(self):
        """Update email_norm and updated_at before replace."""
        self.email_norm = self.email.casefold()
        self.updated_at = datetime.now(timezone.utc)

    @after_event(SaveChanges)
    async def after_save(self):
        """Update updated_at after save."""
        self.updated_at = datetime.now(timezone.utc)

    @after_event(Delete)
    async def after_delete(self):
        """Update updated_at after delete."""
        self.updated_at = datetime.now(timezone.utc)

    @property
    def organization_id(self) -> str:
        """Organization id for the user."""
        org = self.organization
        if hasattr(org, "ref"):
            return str(org.ref.id)
        return str(org.id)
