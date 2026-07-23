"""Unit tests for mindtrace.agents._serialization."""

from __future__ import annotations

import json

from mindtrace.agents._serialization import stringify_tool_result


class TestStringifyToolResult:
    def test_string_passed_through_unchanged(self):
        assert stringify_tool_result("already a string") == "already a string"

    def test_dict_is_json_encoded_not_repr(self):
        result = stringify_tool_result({"answer": 42})
        assert result == '{"answer": 42}'
        assert json.loads(result) == {"answer": 42}

    def test_list_is_json_encoded(self):
        assert stringify_tool_result([1, 2, 3]) == "[1, 2, 3]"

    def test_int_matches_str_behavior(self):
        assert stringify_tool_result(9) == "9"

    def test_bool_and_none_json_encoded(self):
        assert stringify_tool_result(True) == "true"
        assert stringify_tool_result(None) == "null"

    def test_nested_structure_preserved(self):
        value = {"rows": [{"id": 1}, {"id": 2}], "count": 2}
        result = stringify_tool_result(value)
        assert json.loads(result) == value

    def test_non_json_serializable_falls_back_to_str(self):
        value = {1, 2, 3}  # a set has no JSON representation
        assert stringify_tool_result(value) == str(value)

    def test_custom_object_falls_back_to_str(self):
        class Thing:
            def __str__(self) -> str:
                return "a thing"

        assert stringify_tool_result(Thing()) == "a thing"
