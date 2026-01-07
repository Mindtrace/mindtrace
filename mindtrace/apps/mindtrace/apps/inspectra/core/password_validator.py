"""Password validation against configurable policy rules."""

import re
from typing import List, Optional

from mindtrace.apps.inspectra.models.password_policy import (
    PasswordPolicyResponse,
    PasswordValidationResult,
    PolicyRuleResponse,
    PolicyRuleType,
)

# Common passwords list (subset - could be extended or loaded from file)
COMMON_PASSWORDS = {
    "password",
    "123456",
    "password1",
    "12345678",
    "qwerty",
    "abc123",
    "monkey",
    "letmein",
    "dragon",
    "111111",
    "baseball",
    "iloveyou",
    "trustno1",
    "sunshine",
    "master",
    "welcome",
    "shadow",
    "ashley",
    "football",
    "jesus",
    "michael",
    "ninja",
    "mustang",
    "password123",
}


class PasswordValidator:
    """Validates passwords against configurable policy rules."""

    @staticmethod
    def validate(
        password: str, policy: Optional[PasswordPolicyResponse]
    ) -> PasswordValidationResult:
        """
        Validate a password against the given policy.

        Args:
            password: The password to validate
            policy: The password policy to validate against (None = no validation)

        Returns:
            PasswordValidationResult with is_valid flag and list of errors
        """
        if policy is None:
            return PasswordValidationResult(is_valid=True, errors=[])

        errors: List[str] = []
        for rule in policy.rules:
            if not rule.is_active:
                continue

            error = PasswordValidator._validate_rule(password, rule)
            if error:
                errors.append(error)

        return PasswordValidationResult(is_valid=len(errors) == 0, errors=errors)

    @staticmethod
    def _validate_rule(password: str, rule: PolicyRuleResponse) -> Optional[str]:
        """
        Validate a single rule.

        Returns error message if failed, None if passed.
        """
        rule_type = rule.rule_type
        value = rule.value
        message = rule.message

        if rule_type == PolicyRuleType.MIN_LENGTH:
            if len(password) < int(value):
                return message

        elif rule_type == PolicyRuleType.MAX_LENGTH:
            if len(password) > int(value):
                return message

        elif rule_type == PolicyRuleType.REQUIRE_UPPERCASE:
            if value and not any(c.isupper() for c in password):
                return message

        elif rule_type == PolicyRuleType.REQUIRE_LOWERCASE:
            if value and not any(c.islower() for c in password):
                return message

        elif rule_type == PolicyRuleType.REQUIRE_DIGIT:
            if value and not any(c.isdigit() for c in password):
                return message

        elif rule_type == PolicyRuleType.REQUIRE_SPECIAL:
            special_chars = set("!@#$%^&*()_+-=[]{}|;':\",./<>?`~")
            if value and not any(c in special_chars for c in password):
                return message

        elif rule_type == PolicyRuleType.MIN_SPECIAL_COUNT:
            special_chars = set("!@#$%^&*()_+-=[]{}|;':\",./<>?`~")
            count = sum(1 for c in password if c in special_chars)
            if count < int(value):
                return message

        elif rule_type == PolicyRuleType.MIN_DIGIT_COUNT:
            count = sum(1 for c in password if c.isdigit())
            if count < int(value):
                return message

        elif rule_type == PolicyRuleType.MIN_UPPERCASE_COUNT:
            count = sum(1 for c in password if c.isupper())
            if count < int(value):
                return message

        elif rule_type == PolicyRuleType.MIN_LOWERCASE_COUNT:
            count = sum(1 for c in password if c.islower())
            if count < int(value):
                return message

        elif rule_type == PolicyRuleType.DISALLOW_COMMON:
            if value and password.lower() in COMMON_PASSWORDS:
                return message

        elif rule_type == PolicyRuleType.NO_REPEATING_CHARS:
            max_repeat = int(value)
            if max_repeat > 0:
                for i in range(len(password) - max_repeat):
                    if len(set(password[i : i + max_repeat + 1])) == 1:
                        return message

        elif rule_type == PolicyRuleType.CUSTOM_REGEX:
            try:
                if not re.match(str(value), password):
                    return message
            except re.error:
                pass  # Invalid regex, skip rule

        return None
