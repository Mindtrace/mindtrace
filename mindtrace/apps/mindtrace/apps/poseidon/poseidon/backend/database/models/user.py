from typing import List, TYPE_CHECKING, Union
from datetime import datetime, UTC

from beanie import Link, before_event, Insert, Replace, SaveChanges, after_event, Delete
from pydantic import Field
from mindtrace.database import MindtraceDocument
from .enums import OrgRole

if TYPE_CHECKING:
    from .organization import Organization
    from .project import Project

class User(MindtraceDocument):
    # --- identity (no username) ---
    first_name: str
    last_name: str
    email: str  # store lowercased
    password_hash: str  # hashed password
    organization: Link["Organization"]

    # e.g. "user" | "admin" | "super_admin"
    org_role: OrgRole = Field(default=OrgRole.USER.value)

    # --- relationships ---
    projects: List[Link["Project"]] = Field(default_factory=list)

    # --- status & timestamps ---
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # --------------------- lifecycle hooks ---------------------
    @before_event(Insert)
    async def validate_and_set_creation_timestamps(self):
        # Normalize email
        if self.email:
            self.email = self.email.strip().lower()

        # Link must be loaded for validations below
        await self.fetch_link(User.organization)

        # Enforce organization max_users limit
        if not self.organization.is_within_user_limit():
            raise ValueError(f"Organization '{self.organization.id}' has reached its user limit.")

        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now

    @before_event([Replace, SaveChanges])
    def update_timestamp(self):
        # Normalize email on updates as well
        if self.email:
            self.email = self.email.strip().lower()
        self.updated_at = datetime.now(UTC)

    # ---------------------- convenience methods ----------------------

    def has_org_role(self, role: Union[str, OrgRole]) -> bool:
        """Check if user has the specified org-level role (string or enum)."""
        target = getattr(role, "value", role)
        return str(self.org_role) == str(target)

    def add_project(self, project: "Project"):
        """Add a project to the user's list if not already present."""
        if project not in self.projects:
            self.projects.append(project)

    def remove_project(self, project: "Project"):
        """Remove a project from the user's list."""
        self.projects = [p for p in self.projects if p.id != project.id]

    def is_assigned_to_project(self, project: "Project") -> bool:
        """Check if user is assigned to a specific project."""
        return any(p.id == project.id for p in self.projects)

    @after_event(Insert)
    async def increment_org_user_count(self):
        await self.fetch_link(User.organization)
        self.organization.user_count += 1
        await self.organization.save()

    @after_event(Delete)
    async def decrement_org_user_count(self):
        await self.fetch_link(User.organization)
        if self.organization.user_count > 0:
            self.organization.user_count -= 1
            await self.organization.save()
