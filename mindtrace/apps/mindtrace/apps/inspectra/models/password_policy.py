"""Password policy models for configurable password validation rules."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class PolicyRuleType(str, Enum):
    """Supported password policy rule types."""

    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    REQUIRE_UPPERCASE = "require_uppercase"
    REQUIRE_LOWERCASE = "require_lowercase"
    REQUIRE_DIGIT = "require_digit"
    REQUIRE_SPECIAL = "require_special"
    MIN_SPECIAL_COUNT = "min_special_count"
    MIN_DIGIT_COUNT = "min_digit_count"
    MIN_UPPERCASE_COUNT = "min_uppercase_count"
    MIN_LOWERCASE_COUNT = "min_lowercase_count"
    DISALLOW_COMMON = "disallow_common"
    NO_REPEATING_CHARS = "no_repeating_chars"
    CUSTOM_REGEX = "custom_regex"


@dataclass
class PolicyRule:
    """A single password policy rule."""

    id: str
    rule_type: str
    value: Any
    message: str
    is_active: bool = True
    order: int = 0


@dataclass
class PasswordPolicy:
    """Complete password policy configuration."""

    id: str
    name: str
    description: Optional[str] = None
    rules: List[PolicyRule] = field(default_factory=list)
    is_active: bool = True
    is_default: bool = False


# Pydantic request/response models


class PolicyRuleCreateRequest(BaseModel):
    """Request to create a new policy rule."""

    rule_type: str = Field(..., description="Type of rule (from PolicyRuleType)")
    value: Any = Field(..., description="Rule value (int, bool, or str depending on type)")
    message: str = Field(..., description="Error message when validation fails")
    is_active: bool = Field(True, description="Whether rule is active")
    order: int = Field(0, description="Evaluation order (lower = first)")


class PolicyRuleUpdateRequest(BaseModel):
    """Request to update an existing policy rule."""

    id: Optional[str] = Field(None, description="Rule ID (set from path param)")
    rule_type: Optional[str] = Field(None, description="Updated rule type")
    value: Optional[Any] = Field(None, description="Updated rule value")
    message: Optional[str] = Field(None, description="Updated error message")
    is_active: Optional[bool] = Field(None, description="Updated active status")
    order: Optional[int] = Field(None, description="Updated evaluation order")


class PolicyRuleResponse(BaseModel):
    """API response for a policy rule."""

    id: str = Field(..., description="Rule ID")
    rule_type: str = Field(..., description="Type of rule")
    value: Any = Field(..., description="Rule value")
    message: str = Field(..., description="Error message when validation fails")
    is_active: bool = Field(..., description="Whether rule is active")
    order: int = Field(..., description="Evaluation order")


class PasswordPolicyCreateRequest(BaseModel):
    """Request to create a new password policy."""

    name: str = Field(..., description="Policy name", min_length=1)
    description: Optional[str] = Field(None, description="Policy description")
    rules: List[PolicyRuleCreateRequest] = Field(
        default_factory=list, description="Initial rules for the policy"
    )
    is_default: bool = Field(False, description="Set as default policy")


class PasswordPolicyUpdateRequest(BaseModel):
    """Request to update an existing password policy."""

    id: Optional[str] = Field(None, description="Policy ID (set from path param)")
    name: Optional[str] = Field(None, description="Updated policy name")
    description: Optional[str] = Field(None, description="Updated description")
    is_active: Optional[bool] = Field(None, description="Updated active status")
    is_default: Optional[bool] = Field(None, description="Set as default policy")


class PasswordPolicyResponse(BaseModel):
    """API response for a password policy."""

    id: str = Field(..., description="Policy ID")
    name: str = Field(..., description="Policy name")
    description: Optional[str] = Field(None, description="Policy description")
    rules: List[PolicyRuleResponse] = Field(
        default_factory=list, description="Policy rules"
    )
    is_active: bool = Field(..., description="Whether policy is active")
    is_default: bool = Field(..., description="Whether this is the default policy")


class PasswordPolicyListResponse(BaseModel):
    """List response for password policies."""

    items: List[PasswordPolicyResponse] = Field(..., description="List of policies")
    total: int = Field(..., description="Total number of policies")


class PasswordValidationResult(BaseModel):
    """Result of password validation."""

    is_valid: bool = Field(..., description="Whether the password is valid")
    errors: List[str] = Field(
        default_factory=list, description="List of validation error messages"
    )
