"""Unit tests for mindtrace.agents._serialization."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone

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

    def test_non_json_serializable_value_still_becomes_valid_json(self):
        value = {1, 2, 3}  # a set has no JSON representation
        result = stringify_tool_result(value)
        assert json.loads(result) == str(value)

    def test_custom_object_still_becomes_valid_json(self):
        class Thing:
            def __str__(self) -> str:
                return "a thing"

        result = stringify_tool_result(Thing())
        assert json.loads(result) == "a thing"

    def test_dataclass_result_is_json_encoded(self):
        @dataclasses.dataclass
        class ScanVolume:
            scan_count: int
            has_scans: bool

        result = stringify_tool_result(ScanVolume(scan_count=5, has_scans=True))
        assert json.loads(result) == {"scan_count": 5, "has_scans": True}

    def test_dataclass_with_datetime_field_is_json_encoded(self):
        # the real-world case: fastmcp's Client.call_tool() returns a
        # dynamically-generated dataclass (fastmcp.utilities.json_schema_type.Root)
        # for structured tool results, and datetime fields inside it aren't
        # natively JSON-serializable either.
        @dataclasses.dataclass
        class ScanVolume:
            scan_count: int
            latest_scan_ts: datetime

        ts = datetime(2026, 7, 22, 3, 19, 42, tzinfo=timezone.utc)
        result = stringify_tool_result(ScanVolume(scan_count=5, latest_scan_ts=ts))
        decoded = json.loads(result)
        assert decoded["scan_count"] == 5
        assert decoded["latest_scan_ts"] == str(ts)

    def test_pydantic_model_result_is_json_encoded(self):
        from pydantic import BaseModel

        class ScanVolume(BaseModel):
            scan_count: int
            has_scans: bool

        result = stringify_tool_result(ScanVolume(scan_count=5, has_scans=True))
        assert json.loads(result) == {"scan_count": 5, "has_scans": True}
