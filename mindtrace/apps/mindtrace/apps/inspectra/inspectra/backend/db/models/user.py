from datetime import datetime, timezone
from typing import List

from beanie import Delete, Insert, Link, Replace, SaveChanges, after_event, before_event
from inspectra.backend.db.models.enums import UserPersona, UserRole
from inspectra.backend.db.models.line import Line
from inspectra.backend.db.models.organization import Organization
from inspectra.backend.db.models.plant import Plant
from pydantic import EmailStr, Field
from pymongo import IndexModel
from typing_extensions import Any, Dict, Literal, Optional

from mindtrace.database import MindtraceDocument


class User(MindtraceDocument):
    email: EmailStr
    email_norm: str = ""
    role: UserRole = UserRole.user
    persona: Optional[UserPersona] = UserPersona.line_manager
    name: str
    pw_hash: str
    orgs: List[Link[Organization]] = Field(default_factory=list)
    plants: List[Link[Plant]] = Field(default_factory=list)
    lines: List[Link[Line]] = Field(default_factory=list)
    status: Literal["active", "inactive"] = "active"
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)

    async def before_save(self):
        self.email_norm = self.email.casefold()

    class Settings:
        name = "users"
        indexes = [IndexModel([("email_norm", 1)], name="user_email_norm_uq", unique=True)]

    @before_event(Insert)
    async def before_insert(self):
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @before_event(Replace)
    async def before_replace(self):
        self.updated_at = datetime.now(timezone.utc)

    @after_event(SaveChanges)
    async def after_save(self):
        self.updated_at = datetime.now(timezone.utc)

    @after_event(Delete)
    async def after_delete(self):
        self.updated_at = datetime.now(timezone.utc)