"""Repository for password policy CRUD operations using mindtrace.database ODM."""

from typing import List, Optional

from mindtrace.database import DocumentNotFoundError

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.documents import (
    PasswordPolicyDocument,
    PolicyRuleDocument,
)
from mindtrace.apps.inspectra.models.password_policy import (
    PasswordPolicyCreateRequest,
    PasswordPolicyResponse,
    PasswordPolicyUpdateRequest,
    PolicyRuleCreateRequest,
    PolicyRuleResponse,
    PolicyRuleUpdateRequest,
)


class PasswordPolicyRepository:
    """Repository for managing password policies and rules via MongoMindtraceODM."""

    @staticmethod
    def _rule_to_response(doc: PolicyRuleDocument) -> PolicyRuleResponse:
        """Convert PolicyRuleDocument to response model."""
        return PolicyRuleResponse(
            id=str(doc.id),
            rule_type=doc.rule_type,
            value=doc.value,
            message=doc.message,
            is_active=doc.is_active,
            order=doc.order,
        )

    @staticmethod
    def _policy_to_response(
        doc: PasswordPolicyDocument, rules: List[PolicyRuleResponse]
    ) -> PasswordPolicyResponse:
        """Convert PasswordPolicyDocument to response model."""
        return PasswordPolicyResponse(
            id=str(doc.id),
            name=doc.name,
            description=doc.description,
            rules=rules,
            is_active=doc.is_active,
            is_default=doc.is_default,
        )

    async def _get_rules_for_policy(self, policy_id: str) -> List[PolicyRuleResponse]:
        """Get all active rules for a policy, sorted by order."""
        rules = await PolicyRuleDocument.find(
            {"policy_id": policy_id, "is_active": True}
        ).sort("+order").to_list()
        return [self._rule_to_response(r) for r in rules]

    async def get_default_policy(self) -> Optional[PasswordPolicyResponse]:
        """Get the default active password policy."""
        policies = await PasswordPolicyDocument.find(
            {"is_default": True, "is_active": True}
        ).to_list()
        if not policies:
            return None
        policy = policies[0]
        rules = await self._get_rules_for_policy(str(policy.id))
        return self._policy_to_response(policy, rules)

    async def list(self) -> List[PasswordPolicyResponse]:
        """List all password policies with their rules."""
        db = get_db()
        policies = await db.password_policy.all()
        result = []
        for policy in policies:
            rules = await self._get_rules_for_policy(str(policy.id))
            result.append(self._policy_to_response(policy, rules))
        return result

    async def get_by_id(self, policy_id: str) -> Optional[PasswordPolicyResponse]:
        """Get policy by ID with rules."""
        db = get_db()
        try:
            policy = await db.password_policy.get(policy_id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        rules = await self._get_rules_for_policy(policy_id)
        return self._policy_to_response(policy, rules)

    async def create(
        self, payload: PasswordPolicyCreateRequest
    ) -> PasswordPolicyResponse:
        """Create a new password policy with rules."""
        db = get_db()

        # If setting as default, unset other defaults
        if payload.is_default:
            all_policies = await db.password_policy.all()
            for p in all_policies:
                if p.is_default:
                    p.is_default = False
                    await db.password_policy.update(p)

        policy = PasswordPolicyDocument(
            name=payload.name,
            description=payload.description,
            is_active=True,
            is_default=payload.is_default,
        )
        policy = await db.password_policy.insert(policy)
        policy_id = str(policy.id)

        # Create rules
        rules: List[PolicyRuleResponse] = []
        for rule in payload.rules:
            rule_resp = await self.add_rule(policy_id, rule)
            rules.append(rule_resp)

        return self._policy_to_response(policy, rules)

    async def update(
        self, payload: PasswordPolicyUpdateRequest
    ) -> Optional[PasswordPolicyResponse]:
        """Update a password policy."""
        db = get_db()
        try:
            policy = await db.password_policy.get(payload.id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        # If setting as default, unset other defaults
        if payload.is_default:
            all_policies = await db.password_policy.all()
            for p in all_policies:
                if p.is_default and str(p.id) != payload.id:
                    p.is_default = False
                    await db.password_policy.update(p)

        if payload.name is not None:
            policy.name = payload.name
        if payload.description is not None:
            policy.description = payload.description
        if payload.is_active is not None:
            policy.is_active = payload.is_active
        if payload.is_default is not None:
            policy.is_default = payload.is_default

        await db.password_policy.update(policy)
        return await self.get_by_id(payload.id)

    async def delete(self, policy_id: str) -> bool:
        """Delete a policy and all its rules."""
        db = get_db()

        # Delete all rules for this policy
        rules = await PolicyRuleDocument.find({"policy_id": policy_id}).to_list()
        for rule in rules:
            await db.policy_rule.delete(str(rule.id))

        try:
            await db.password_policy.delete(policy_id)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False

    async def add_rule(
        self, policy_id: str, rule: PolicyRuleCreateRequest
    ) -> PolicyRuleResponse:
        """Add a rule to a policy."""
        db = get_db()
        rule_doc = PolicyRuleDocument(
            policy_id=policy_id,
            rule_type=rule.rule_type,
            value=rule.value,
            message=rule.message,
            is_active=rule.is_active,
            order=rule.order,
        )
        rule_doc = await db.policy_rule.insert(rule_doc)
        return self._rule_to_response(rule_doc)

    async def get_rule_by_id(self, rule_id: str) -> Optional[PolicyRuleResponse]:
        """Get a rule by ID."""
        db = get_db()
        try:
            rule = await db.policy_rule.get(rule_id)
            return self._rule_to_response(rule)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

    async def update_rule(
        self, payload: PolicyRuleUpdateRequest
    ) -> Optional[PolicyRuleResponse]:
        """Update an existing rule."""
        db = get_db()
        try:
            rule = await db.policy_rule.get(payload.id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        if payload.rule_type is not None:
            rule.rule_type = payload.rule_type
        if payload.value is not None:
            rule.value = payload.value
        if payload.message is not None:
            rule.message = payload.message
        if payload.is_active is not None:
            rule.is_active = payload.is_active
        if payload.order is not None:
            rule.order = payload.order

        await db.policy_rule.update(rule)
        return self._rule_to_response(rule)

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule."""
        db = get_db()
        try:
            await db.policy_rule.delete(rule_id)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False
