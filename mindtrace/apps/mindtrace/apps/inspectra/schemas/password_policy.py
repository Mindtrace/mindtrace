"""TaskSchemas for password policy operations in Inspectra."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models.password_policy import (
    PasswordPolicyCreateRequest,
    PasswordPolicyListResponse,
    PasswordPolicyResponse,
    PasswordPolicyUpdateRequest,
    PasswordValidationResult,
    PolicyRuleCreateRequest,
    PolicyRuleResponse,
    PolicyRuleUpdateRequest,
)
from mindtrace.core import TaskSchema


class PolicyIdRequest(BaseModel):
    """Request with policy ID."""

    id: str = Field(..., description="Policy ID")


class RuleIdRequest(BaseModel):
    """Request with rule ID."""

    id: str = Field(..., description="Rule ID")


class AddRuleRequest(PolicyRuleCreateRequest):
    """Request to add a rule to a policy (policy_id comes from path)."""

    policy_id: Optional[str] = Field(None, description="Policy ID (set from path param)")


class ValidatePasswordRequest(BaseModel):
    """Request to validate a password against the default policy."""

    password: str = Field(..., description="Password to validate")


# Password Policy TaskSchemas
ListPasswordPoliciesSchema = TaskSchema(
    name="inspectra_list_password_policies",
    input_schema=None,
    output_schema=PasswordPolicyListResponse,
)

GetPasswordPolicySchema = TaskSchema(
    name="inspectra_get_password_policy",
    input_schema=PolicyIdRequest,
    output_schema=PasswordPolicyResponse,
)

CreatePasswordPolicySchema = TaskSchema(
    name="inspectra_create_password_policy",
    input_schema=PasswordPolicyCreateRequest,
    output_schema=PasswordPolicyResponse,
)

UpdatePasswordPolicySchema = TaskSchema(
    name="inspectra_update_password_policy",
    input_schema=PasswordPolicyUpdateRequest,
    output_schema=PasswordPolicyResponse,
)

DeletePasswordPolicySchema = TaskSchema(
    name="inspectra_delete_password_policy",
    input_schema=PolicyIdRequest,
    output_schema=None,
)

# Policy Rule TaskSchemas
AddPolicyRuleSchema = TaskSchema(
    name="inspectra_add_policy_rule",
    input_schema=AddRuleRequest,
    output_schema=PolicyRuleResponse,
)

UpdatePolicyRuleSchema = TaskSchema(
    name="inspectra_update_policy_rule",
    input_schema=PolicyRuleUpdateRequest,
    output_schema=PolicyRuleResponse,
)

DeletePolicyRuleSchema = TaskSchema(
    name="inspectra_delete_policy_rule",
    input_schema=RuleIdRequest,
    output_schema=None,
)

# Password Validation TaskSchema
ValidatePasswordSchema = TaskSchema(
    name="inspectra_validate_password",
    input_schema=ValidatePasswordRequest,
    output_schema=PasswordValidationResult,
)

__all__ = [
    "PolicyIdRequest",
    "RuleIdRequest",
    "AddRuleRequest",
    "ValidatePasswordRequest",
    "ListPasswordPoliciesSchema",
    "GetPasswordPolicySchema",
    "CreatePasswordPolicySchema",
    "UpdatePasswordPolicySchema",
    "DeletePasswordPolicySchema",
    "AddPolicyRuleSchema",
    "UpdatePolicyRuleSchema",
    "DeletePolicyRuleSchema",
    "ValidatePasswordSchema",
]
