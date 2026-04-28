"""Validation tests for PLC service request models."""

import pytest
from pydantic import ValidationError

from mindtrace.hardware.services.plcs.models.requests import (
    TagBatchReadRequest,
    TagBatchWriteRequest,
    TagReadRequest,
    TagWriteRequest,
)


class TestTagReadRequest:
    def test_rejects_empty_tag_list(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            TagReadRequest(plc="p1", tags=[])

    def test_rejects_blank_string_tag(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            TagReadRequest(plc="p1", tags="   ")

    def test_accepts_non_blank_string_tag(self) -> None:
        req = TagReadRequest(plc="p1", tags="  MyTag  ")
        assert req.tags == "  MyTag  "


class TestTagWriteRequest:
    def test_accepts_list_of_pairs(self) -> None:
        req = TagWriteRequest(plc="p1", tags=[("a", 1), ("b", 2)])
        assert req.tags == [("a", 1), ("b", 2)]

    def test_rejects_empty_write_list(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            TagWriteRequest(plc="p1", tags=[])

    def test_rejects_malformed_tuple_in_list(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagWriteRequest(plc="p1", tags=[("only_one",)])

    def test_rejects_non_pair_element_in_list(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagWriteRequest(plc="p1", tags=[("a", 1), "not-a-pair"])  # type: ignore[list-item]

    def test_single_tuple_accepts_pair(self) -> None:
        req = TagWriteRequest(plc="p1", tags=("MyTag", 42))
        assert req.tags == ("MyTag", 42)

    def test_rejects_single_tuple_wrong_length(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagWriteRequest(plc="p1", tags=(1, 2, 3))  # type: ignore[arg-type]

    def test_rejects_non_tuple_tags(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagWriteRequest(plc="p1", tags="bad")  # type: ignore[arg-type]


class TestTagBatchReadRequest:
    def test_accepts_well_formed_rows(self) -> None:
        req = TagBatchReadRequest(requests=[("plc1", ["a", "b"]), ("plc2", "single")])
        assert len(req.requests) == 2

    def test_rejects_empty_requests(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            TagBatchReadRequest(requests=[])

    def test_rejects_malformed_row(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagBatchReadRequest(requests=[("plc",)])  # type: ignore[list-item]

    def test_rejects_row_that_is_not_tuple_or_list(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagBatchReadRequest(requests=[{"plc": "x", "tags": ["a"]}])  # type: ignore[list-item]

    def test_rejects_row_wrong_length(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagBatchReadRequest(requests=[("plc", "t1", "extra")])  # type: ignore[list-item]


class TestTagBatchWriteRequest:
    def test_accepts_well_formed_rows(self) -> None:
        req = TagBatchWriteRequest(
            requests=[
                ("plc1", [("t", 1)]),
                ("plc2", ("t2", 2)),
            ]
        )
        assert len(req.requests) == 2

    def test_rejects_empty_requests(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            TagBatchWriteRequest(requests=[])

    def test_rejects_malformed_row(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagBatchWriteRequest(requests=[("plc", "not_tuple_or_list")])  # type: ignore[list-item]

    def test_rejects_row_that_is_not_tuple_or_list(self) -> None:
        with pytest.raises(ValidationError, match="tuple"):
            TagBatchWriteRequest(requests=[None])  # type: ignore[list-item]

    def test_rejects_row_wrong_length(self) -> None:
        with pytest.raises(ValidationError):
            TagBatchWriteRequest(requests=[["plc", "tags", "extra"]])  # type: ignore[list-item]


class TestTagValidatorsDirect:
    """Exercise ``field_validator`` bodies that Pydantic may shortcut during model init."""

    def test_write_tags_list_element_not_pair(self) -> None:
        with pytest.raises(ValueError, match="tuple"):
            TagWriteRequest.validate_tags([("a", 1), "nope"])  # type: ignore[list-item]

    def test_write_tags_single_sequence_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="tuple"):
            TagWriteRequest.validate_tags((1, 2, 3))

    def test_write_tags_not_tuple_or_list(self) -> None:
        with pytest.raises(ValueError, match="tuple"):
            TagWriteRequest.validate_tags(123)  # type: ignore[arg-type]

    def test_batch_read_row_validation(self) -> None:
        with pytest.raises(ValueError, match="tuple"):
            TagBatchReadRequest.validate_requests([("only_one",)])  # type: ignore[list-item]

    def test_batch_write_row_validation(self) -> None:
        with pytest.raises(ValueError, match="tuple"):
            TagBatchWriteRequest.validate_requests([None])  # type: ignore[list-item]
