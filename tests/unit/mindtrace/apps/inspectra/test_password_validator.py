"""Unit tests for password validation against configurable policies."""

import pytest

from mindtrace.apps.inspectra.core.password_validator import PasswordValidator
from mindtrace.apps.inspectra.models.password_policy import (
    PasswordPolicyResponse,
    PasswordValidationResult,
    PolicyRuleResponse,
    PolicyRuleType,
)


class TestPasswordValidator:
    """
    Unit tests for PasswordValidator.

    Tests validate:
    - Password validation against various rule types
    - Multiple rules combination
    - Empty/no policy handling
    """

    def _make_policy(self, rules: list[PolicyRuleResponse]) -> PasswordPolicyResponse:
        """Helper to create a policy with given rules."""
        return PasswordPolicyResponse(
            id="test-policy",
            name="Test Policy",
            description="Policy for testing",
            rules=rules,
            is_active=True,
            is_default=True,
        )

    def _make_rule(
        self, rule_type: str, value, message: str, order: int = 0
    ) -> PolicyRuleResponse:
        """Helper to create a rule."""
        return PolicyRuleResponse(
            id=f"rule-{order}",
            rule_type=rule_type,
            value=value,
            message=message,
            is_active=True,
            order=order,
        )

    def test_no_policy_returns_valid(self):
        """Validation with no policy should always pass."""
        result = PasswordValidator.validate("any-password", None)

        assert result.is_valid is True
        assert result.errors == []

    def test_min_length_pass(self):
        """Password meeting minimum length should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_LENGTH, 8, "Must be at least 8 chars")
        ])

        result = PasswordValidator.validate("password123", policy)

        assert result.is_valid is True

    def test_min_length_fail(self):
        """Password below minimum length should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_LENGTH, 8, "Must be at least 8 chars")
        ])

        result = PasswordValidator.validate("short", policy)

        assert result.is_valid is False
        assert "Must be at least 8 chars" in result.errors

    def test_max_length_pass(self):
        """Password within maximum length should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MAX_LENGTH, 20, "Must be at most 20 chars")
        ])

        result = PasswordValidator.validate("normalpassword", policy)

        assert result.is_valid is True

    def test_max_length_fail(self):
        """Password exceeding maximum length should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MAX_LENGTH, 10, "Must be at most 10 chars")
        ])

        result = PasswordValidator.validate("verylongpassword", policy)

        assert result.is_valid is False
        assert "Must be at most 10 chars" in result.errors

    def test_require_uppercase_pass(self):
        """Password with uppercase should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_UPPERCASE, True, "Must have uppercase")
        ])

        result = PasswordValidator.validate("Password", policy)

        assert result.is_valid is True

    def test_require_uppercase_fail(self):
        """Password without uppercase should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_UPPERCASE, True, "Must have uppercase")
        ])

        result = PasswordValidator.validate("password", policy)

        assert result.is_valid is False
        assert "Must have uppercase" in result.errors

    def test_require_lowercase_pass(self):
        """Password with lowercase should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_LOWERCASE, True, "Must have lowercase")
        ])

        result = PasswordValidator.validate("PASSWORDa", policy)

        assert result.is_valid is True

    def test_require_lowercase_fail(self):
        """Password without lowercase should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_LOWERCASE, True, "Must have lowercase")
        ])

        result = PasswordValidator.validate("PASSWORD123", policy)

        assert result.is_valid is False
        assert "Must have lowercase" in result.errors

    def test_require_digit_pass(self):
        """Password with digit should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_DIGIT, True, "Must have digit")
        ])

        result = PasswordValidator.validate("password1", policy)

        assert result.is_valid is True

    def test_require_digit_fail(self):
        """Password without digit should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_DIGIT, True, "Must have digit")
        ])

        result = PasswordValidator.validate("password", policy)

        assert result.is_valid is False
        assert "Must have digit" in result.errors

    def test_require_special_pass(self):
        """Password with special character should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_SPECIAL, True, "Must have special char")
        ])

        result = PasswordValidator.validate("password!", policy)

        assert result.is_valid is True

    def test_require_special_fail(self):
        """Password without special character should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.REQUIRE_SPECIAL, True, "Must have special char")
        ])

        result = PasswordValidator.validate("password123", policy)

        assert result.is_valid is False
        assert "Must have special char" in result.errors

    def test_min_special_count_pass(self):
        """Password with enough special characters should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_SPECIAL_COUNT, 2, "Must have 2+ special chars")
        ])

        result = PasswordValidator.validate("pass!word@", policy)

        assert result.is_valid is True

    def test_min_special_count_fail(self):
        """Password with too few special characters should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_SPECIAL_COUNT, 2, "Must have 2+ special chars")
        ])

        result = PasswordValidator.validate("password!", policy)

        assert result.is_valid is False
        assert "Must have 2+ special chars" in result.errors

    def test_min_digit_count_pass(self):
        """Password with enough digits should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_DIGIT_COUNT, 2, "Must have 2+ digits")
        ])

        result = PasswordValidator.validate("pass12word", policy)

        assert result.is_valid is True

    def test_min_digit_count_fail(self):
        """Password with too few digits should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_DIGIT_COUNT, 2, "Must have 2+ digits")
        ])

        result = PasswordValidator.validate("password1", policy)

        assert result.is_valid is False
        assert "Must have 2+ digits" in result.errors

    def test_disallow_common_pass(self):
        """Non-common password should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.DISALLOW_COMMON, True, "Cannot use common password")
        ])

        result = PasswordValidator.validate("myUniqueP@ss123", policy)

        assert result.is_valid is True

    def test_disallow_common_fail(self):
        """Common password should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.DISALLOW_COMMON, True, "Cannot use common password")
        ])

        result = PasswordValidator.validate("password", policy)

        assert result.is_valid is False
        assert "Cannot use common password" in result.errors

    def test_no_repeating_chars_pass(self):
        """Password without repeating chars should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.NO_REPEATING_CHARS, 3, "No 3+ repeating chars")
        ])

        result = PasswordValidator.validate("paassword", policy)  # 'aa' is only 2

        assert result.is_valid is True

    def test_no_repeating_chars_fail(self):
        """Password with repeating chars should fail."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.NO_REPEATING_CHARS, 2, "No 3+ repeating chars")
        ])

        result = PasswordValidator.validate("paaassword", policy)  # 'aaa' is 3

        assert result.is_valid is False
        assert "No 3+ repeating chars" in result.errors

    def test_custom_regex_pass(self):
        """Password matching custom regex should pass."""
        policy = self._make_policy([
            self._make_rule(
                PolicyRuleType.CUSTOM_REGEX,
                r"^[A-Z].*[0-9]$",
                "Must start with uppercase and end with digit"
            )
        ])

        result = PasswordValidator.validate("Password1", policy)

        assert result.is_valid is True

    def test_custom_regex_fail(self):
        """Password not matching custom regex should fail."""
        policy = self._make_policy([
            self._make_rule(
                PolicyRuleType.CUSTOM_REGEX,
                r"^[A-Z].*[0-9]$",
                "Must start with uppercase and end with digit"
            )
        ])

        result = PasswordValidator.validate("password", policy)

        assert result.is_valid is False
        assert "Must start with uppercase and end with digit" in result.errors

    def test_multiple_rules_all_pass(self):
        """Password meeting all rules should pass."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_LENGTH, 8, "Min 8 chars", 0),
            self._make_rule(PolicyRuleType.REQUIRE_UPPERCASE, True, "Need uppercase", 1),
            self._make_rule(PolicyRuleType.REQUIRE_DIGIT, True, "Need digit", 2),
        ])

        result = PasswordValidator.validate("Password1", policy)

        assert result.is_valid is True
        assert result.errors == []

    def test_multiple_rules_some_fail(self):
        """Password failing some rules should return all failures."""
        policy = self._make_policy([
            self._make_rule(PolicyRuleType.MIN_LENGTH, 8, "Min 8 chars", 0),
            self._make_rule(PolicyRuleType.REQUIRE_UPPERCASE, True, "Need uppercase", 1),
            self._make_rule(PolicyRuleType.REQUIRE_DIGIT, True, "Need digit", 2),
        ])

        result = PasswordValidator.validate("short", policy)

        assert result.is_valid is False
        assert "Min 8 chars" in result.errors
        assert "Need uppercase" in result.errors
        assert "Need digit" in result.errors

    def test_inactive_rule_is_skipped(self):
        """Inactive rules should not be evaluated."""
        inactive_rule = PolicyRuleResponse(
            id="inactive",
            rule_type=PolicyRuleType.MIN_LENGTH,
            value=100,
            message="Must be 100+ chars",
            is_active=False,
            order=0,
        )
        policy = self._make_policy([inactive_rule])

        result = PasswordValidator.validate("short", policy)

        assert result.is_valid is True
