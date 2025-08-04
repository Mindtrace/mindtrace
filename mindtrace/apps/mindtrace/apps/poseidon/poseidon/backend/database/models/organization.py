from mindtrace.database import MindtraceDocument
from typing import Dict, Optional
from datetime import datetime, UTC
import secrets
from pydantic import Field
from beanie import before_event, Insert, Replace, SaveChanges
from .enums import SubscriptionPlan

class Organization(MindtraceDocument):
    name: str
    description: Optional[str] = ""
    settings: Dict = Field(default_factory=dict)

    # Admin registration key for this organization
    admin_registration_key: str = Field(default_factory=lambda: f"ORG_{secrets.token_urlsafe(32)}")

    # Subscription/plan info
    subscription_plan: SubscriptionPlan = SubscriptionPlan.BASIC
    max_users: Optional[int] = None
    max_projects: Optional[int] = None
    user_count: int = 0

    # Status
    is_active: bool = True

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @before_event([Insert])
    def set_defaults_on_insert(self):
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        if not self.admin_registration_key:
            self.admin_registration_key = f"ORG_{secrets.token_urlsafe(32)}"

    @before_event([Replace, SaveChanges])
    def update_timestamp_on_update(self):
        self.updated_at = datetime.now(UTC)

    def get_setting(self, key: str, default=None):
        """Get a specific setting value"""
        return self.settings.get(key, default)

    def update_setting(self, key: str, value):
        """Update a specific setting"""
        self.settings[key] = value

    def is_within_user_limit(self) -> bool:
        return self.max_users is None or self.user_count < self.max_users
    
    def generate_admin_key(self) -> str:
        """Generate a secure admin registration key"""
        return f"ORG_{secrets.token_urlsafe(32)}"
    
    def regenerate_admin_key(self):
        """Regenerate the admin registration key"""
        self.admin_registration_key = f"ORG_{secrets.token_urlsafe(32)}"