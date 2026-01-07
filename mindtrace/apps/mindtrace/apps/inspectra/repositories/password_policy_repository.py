"""Repository for password policy CRUD operations."""

import inspect
from typing import Any, List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.password_policy import (
    PasswordPolicyCreateRequest,
    PasswordPolicyResponse,
    PasswordPolicyUpdateRequest,
    PolicyRuleCreateRequest,
    PolicyRuleResponse,
    PolicyRuleUpdateRequest,
)


class PasswordPolicyRepository:
    """Repository for managing password policies and rules in MongoDB."""

    def __init__(self) -> None:
        self._policies_collection_name = "password_policies"
        self._rules_collection_name = "policy_rules"

    def _policies_collection(self):
        db = get_db()
        return db[self._policies_collection_name]

    def _rules_collection(self):
        db = get_db()
        return db[self._rules_collection_name]

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    @staticmethod
    def _rule_to_model(doc: dict) -> PolicyRuleResponse:
        return PolicyRuleResponse(
            id=str(doc["_id"]),
            rule_type=doc["rule_type"],
            value=doc["value"],
            message=doc["message"],
            is_active=doc.get("is_active", True),
            order=doc.get("order", 0),
        )

    def _policy_to_model(
        self, doc: dict, rules: List[PolicyRuleResponse]
    ) -> PasswordPolicyResponse:
        return PasswordPolicyResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            description=doc.get("description"),
            rules=rules,
            is_active=doc.get("is_active", True),
            is_default=doc.get("is_default", False),
        )

    async def _get_rules_for_policy(self, policy_id: str) -> List[PolicyRuleResponse]:
        """Get all active rules for a policy, sorted by order."""
        cursor = (
            self._rules_collection()
            .find({"policy_id": policy_id, "is_active": True})
            .sort("order", 1)
        )
        rules: List[PolicyRuleResponse] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                rules.append(self._rule_to_model(doc))
        else:
            for doc in cursor:
                rules.append(self._rule_to_model(doc))

        return rules

    async def get_default_policy(self) -> Optional[PasswordPolicyResponse]:
        """Get the default active password policy."""
        doc = await self._maybe_await(
            self._policies_collection().find_one({"is_default": True, "is_active": True})
        )
        if not doc:
            return None
        rules = await self._get_rules_for_policy(str(doc["_id"]))
        return self._policy_to_model(doc, rules)

    async def list(self) -> List[PasswordPolicyResponse]:
        """List all password policies."""
        cursor = self._policies_collection().find({})
        policies: List[PasswordPolicyResponse] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                rules = await self._get_rules_for_policy(str(doc["_id"]))
                policies.append(self._policy_to_model(doc, rules))
        else:
            for doc in cursor:
                rules = await self._get_rules_for_policy(str(doc["_id"]))
                policies.append(self._policy_to_model(doc, rules))

        return policies

    async def get_by_id(self, policy_id: str) -> Optional[PasswordPolicyResponse]:
        """Get policy by ID."""
        try:
            oid = ObjectId(policy_id)
        except Exception:
            return None

        doc = await self._maybe_await(
            self._policies_collection().find_one({"_id": oid})
        )
        if not doc:
            return None

        rules = await self._get_rules_for_policy(policy_id)
        return self._policy_to_model(doc, rules)

    async def create(
        self, payload: PasswordPolicyCreateRequest
    ) -> PasswordPolicyResponse:
        """Create a new password policy with rules."""
        # If setting as default, unset other defaults
        if payload.is_default:
            await self._maybe_await(
                self._policies_collection().update_many(
                    {}, {"$set": {"is_default": False}}
                )
            )

        data = {
            "name": payload.name,
            "description": payload.description,
            "is_active": True,
            "is_default": payload.is_default,
        }
        result = await self._maybe_await(self._policies_collection().insert_one(data))
        policy_id = str(result.inserted_id)

        # Create rules
        rules: List[PolicyRuleResponse] = []
        for rule in payload.rules:
            rule_resp = await self.add_rule(policy_id, rule)
            rules.append(rule_resp)

        data["_id"] = result.inserted_id
        return self._policy_to_model(data, rules)

    async def update(
        self, payload: PasswordPolicyUpdateRequest
    ) -> Optional[PasswordPolicyResponse]:
        """Update a password policy."""
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        # If setting as default, unset other defaults
        if payload.is_default:
            await self._maybe_await(
                self._policies_collection().update_many(
                    {}, {"$set": {"is_default": False}}
                )
            )

        update_data: dict[str, Any] = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.description is not None:
            update_data["description"] = payload.description
        if payload.is_active is not None:
            update_data["is_active"] = payload.is_active
        if payload.is_default is not None:
            update_data["is_default"] = payload.is_default

        if update_data:
            await self._maybe_await(
                self._policies_collection().update_one(
                    {"_id": oid}, {"$set": update_data}
                )
            )

        return await self.get_by_id(payload.id)

    async def delete(self, policy_id: str) -> bool:
        """Delete a policy and all its rules."""
        try:
            oid = ObjectId(policy_id)
        except Exception:
            return False

        # Delete all rules for this policy
        await self._maybe_await(
            self._rules_collection().delete_many({"policy_id": policy_id})
        )

        result = await self._maybe_await(
            self._policies_collection().delete_one({"_id": oid})
        )
        return result.deleted_count > 0

    async def add_rule(
        self, policy_id: str, rule: PolicyRuleCreateRequest
    ) -> PolicyRuleResponse:
        """Add a rule to a policy."""
        data = {
            "policy_id": policy_id,
            "rule_type": rule.rule_type,
            "value": rule.value,
            "message": rule.message,
            "is_active": rule.is_active,
            "order": rule.order,
        }
        result = await self._maybe_await(self._rules_collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._rule_to_model(data)

    async def get_rule_by_id(self, rule_id: str) -> Optional[PolicyRuleResponse]:
        """Get a rule by ID."""
        try:
            oid = ObjectId(rule_id)
        except Exception:
            return None

        doc = await self._maybe_await(self._rules_collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._rule_to_model(doc)

    async def update_rule(
        self, payload: PolicyRuleUpdateRequest
    ) -> Optional[PolicyRuleResponse]:
        """Update an existing rule."""
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        update_data: dict[str, Any] = {}
        if payload.rule_type is not None:
            update_data["rule_type"] = payload.rule_type
        if payload.value is not None:
            update_data["value"] = payload.value
        if payload.message is not None:
            update_data["message"] = payload.message
        if payload.is_active is not None:
            update_data["is_active"] = payload.is_active
        if payload.order is not None:
            update_data["order"] = payload.order

        if update_data:
            await self._maybe_await(
                self._rules_collection().update_one({"_id": oid}, {"$set": update_data})
            )

        doc = await self._maybe_await(self._rules_collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._rule_to_model(doc)

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule."""
        try:
            oid = ObjectId(rule_id)
        except Exception:
            return False

        result = await self._maybe_await(
            self._rules_collection().delete_one({"_id": oid})
        )
        return result.deleted_count > 0
