"""User model for the Inspectra application."""

from datetime import datetime, timezone
from typing import List

from beanie import Delete, Insert, Link, Replace, SaveChanges, after_event, before_event
from pydantic import EmailStr, Field
from typing_extensions import Any, Dict, Literal

from mindtrace.apps.inspectra.models.enums import UserRole
from mindtrace.apps.inspectra.models.line import Line
from mindtrace.apps.inspectra.models.organization import Organization
from mindtrace.apps.inspectra.models.plant import Plant
from mindtrace.database import MindtraceDocument


class User(MindtraceDocument):
    """User model representing a system user."""

    organization: Link[Organization]
    email: EmailStr
    email_norm: str = ""
    role: UserRole
    first_name: str
    last_name: str
    pw_hash: str
    plants: List[Link[Plant]] = Field(default_factory=list)
    lines: List[Link[Line]] = Field(default_factory=list)
    status: Literal["active", "inactive"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    async def before_save(self):
        """Normalize email to lowercase before saving."""
        self.email_norm = self.email.casefold()

    class Settings:
        """Beanie settings for the User collection."""

        name = "users"

    @before_event(Insert)
    async def before_insert(self):
        """Set created_at and updated_at timestamps before document insertion."""
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @before_event(Replace)
    async def before_replace(self):
        """Update updated_at timestamp before document replacement."""
        self.updated_at = datetime.now(timezone.utc)

    @after_event(SaveChanges)
    async def after_save(self):
        """Update updated_at timestamp after document save."""
        self.updated_at = datetime.now(timezone.utc)

    @after_event(Delete)
    async def after_delete(self):
        """Update updated_at timestamp after document deletion."""
        self.updated_at = datetime.now(timezone.utc)
