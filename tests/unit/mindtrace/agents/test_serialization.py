"""Unit tests for mindtrace.agents._serialization."""

from __future__ import annotations

import dataclasses
import json
import threading
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
        # ISO 8601 ("...T03:19:42+00:00"), not str(datetime)'s space separator
        assert decoded["latest_scan_ts"] == ts.isoformat()

    def test_pydantic_model_result_is_json_encoded(self):
        from pydantic import BaseModel

        class ScanVolume(BaseModel):
            scan_count: int
            has_scans: bool

        result = stringify_tool_result(ScanVolume(scan_count=5, has_scans=True))
        assert json.loads(result) == {"scan_count": 5, "has_scans": True}

    def test_datetime_uses_iso_format(self):
        ts = datetime(2026, 7, 22, 3, 19, 42, tzinfo=timezone.utc)
        assert json.loads(stringify_tool_result({"ts": ts})) == {"ts": "2026-07-22T03:19:42+00:00"}


class TestStringifyToolResultNeverRaises:
    """Callers run this inside the ``try`` that turns tool exceptions into
    ``"Error: ..."`` content, so a serialization failure would be reported to
    the model as a *tool* failure — for a tool call that actually succeeded.
    Every value must degrade to ``str()`` instead of raising."""

    def test_circular_reference_falls_back_to_str(self):
        value: dict = {}
        value["self"] = value  # json.dumps raises ValueError, not TypeError
        assert stringify_tool_result(value) == str(value)

    def test_dataclass_with_non_copyable_field_falls_back_to_str(self):
        # dataclasses.asdict() deepcopies field values; a lock can't be pickled
        @dataclasses.dataclass
        class Handle:
            name: str
            lock: object

        value = Handle(name="scanner-1", lock=threading.Lock())
        assert stringify_tool_result(value) == str(value)

    def test_non_callable_model_dump_attribute_falls_back_to_str(self):
        class NotAModel:
            model_dump = "not callable"

        value = NotAModel()
        assert stringify_tool_result(value) == str(value)

    def test_raising_model_dump_falls_back_to_str(self):
        class Exploding:
            def model_dump(self, **kwargs):
                raise RuntimeError("boom")

        value = Exploding()
        assert stringify_tool_result(value) == str(value)
