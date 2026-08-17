"""Tests for canonical camera configuration normalization."""

from mindtrace.hardware.cameras.core.configuration import (
    ConfigurationApplyResult,
    applied_settings_from_result,
    applied_subset_from_exception,
    configuration_error_result,
    find_skipped_keys,
    merge_configure_settings,
    normalize_settings,
    parse_configure_settings,
    settings_to_camera_configuration_dict,
)


def test_normalize_settings_maps_legacy_aliases():
    data = {
        "camera_type": "basler",
        "timestamp": 1.0,
        "exposure": 12000.0,
        "triggermode": "trigger",
        "img_quality_enhancement": True,
        "roi": {"x": 1, "y": 2, "width": 640, "height": 480},
    }

    normalized = normalize_settings(data)

    assert normalized["exposure_time"] == 12000.0
    assert normalized["trigger_mode"] == "trigger"
    assert normalized["image_enhancement"] is True
    assert normalized["roi"] == (1, 2, 640, 480)
    assert "camera_type" not in normalized
    assert "timestamp" not in normalized


def test_normalize_settings_supports_roi_x_y_fallback():
    data = {"roi_x": 5, "roi_y": 6, "width": 800, "height": 600, "gain": 2.0}

    normalized = normalize_settings(data)

    assert normalized["roi"] == (5, 6, 800, 600)
    assert normalized["gain"] == 2.0


def test_settings_to_camera_configuration_dict_includes_backend_specific_keys():
    data = {
        "camera_type": "basler",
        "exposure_time": 1000.0,
        "focus_config": {"mode": "auto"},
        "genicam_nodes": {"PixelFormat": "Mono8"},
        "brightness": 0.5,
    }

    mapped = settings_to_camera_configuration_dict(data)

    assert mapped["exposure_time"] == 1000.0
    assert mapped["focus_config"] == {"mode": "auto"}
    assert mapped["genicam_nodes"] == {"PixelFormat": "Mono8"}
    assert mapped["brightness"] == 0.5
    assert "camera_type" not in mapped


def test_configuration_apply_result_success_property():
    assert ConfigurationApplyResult(applied=3, total=3).success is True
    assert ConfigurationApplyResult(applied=0, total=0).success is True
    assert ConfigurationApplyResult(applied=2, total=5).success is False
    assert ConfigurationApplyResult(applied=0, total=0, skipped=("exposre_time",)).success is False
    assert ConfigurationApplyResult(applied=1, total=1, skipped=("camera_type",)).success is True


def test_configuration_error_result_uses_payload_size_with_floor_of_one():
    two_keys = configuration_error_result("not initialized", {"exposure": 1000, "gain": 2.0})
    assert two_keys.applied == 0
    assert two_keys.total == 2
    assert two_keys.success is False
    assert two_keys.failures == {"_error": "not initialized"}

    empty = configuration_error_result("not initialized", {})
    assert empty.total == 1
    assert empty.success is False

    missing = configuration_error_result("not initialized")
    assert missing.total == 1
    assert missing.success is False


def test_applied_settings_from_result_returns_only_successful_keys():
    raw = {"exposure": 15000, "gain": 4.0, "camera_type": "basler"}
    result = ConfigurationApplyResult(
        applied=1,
        total=2,
        failures={"gain": "out of range"},
    )

    applied = applied_settings_from_result(raw, result)

    assert applied == {"exposure_time": 15000}
    assert "gain" not in applied


def test_applied_settings_from_result_empty_when_nothing_applied():
    raw = {"exposure_time": 15000, "gain": 4.0}
    result = ConfigurationApplyResult(applied=0, total=2, failures={"exposure_time": "bad", "gain": "bad"})

    assert applied_settings_from_result(raw, result) == {}


def test_applied_settings_from_result_keeps_partial_nested_genicam_nodes():
    raw = {"genicam_nodes": {"PixelFormat": "Mono8", "ReverseX": True}}
    result = ConfigurationApplyResult(
        applied=0,
        total=1,
        failures={"genicam_nodes": "ReverseX: not writable"},
        partial={"genicam_nodes": {"PixelFormat": "Mono8"}},
    )

    assert applied_settings_from_result(raw, result) == {"genicam_nodes": {"PixelFormat": "Mono8"}}


def test_merge_configure_settings_accumulates_nested_keys():
    existing = {"exposure_time": 15000, "genicam_nodes": {"PixelFormat": "Mono8"}}

    merge_configure_settings(
        existing,
        {"genicam_nodes": {"ReverseX": True}, "gain": 4.0},
        nested_merge_keys=("genicam_nodes",),
    )

    assert existing == {
        "exposure_time": 15000,
        "gain": 4.0,
        "genicam_nodes": {"PixelFormat": "Mono8", "ReverseX": True},
    }


def test_merge_configure_settings_overwrites_existing_nested_values():
    existing = {"genicam_nodes": {"PixelFormat": "Mono8", "ReverseX": False}}

    merge_configure_settings(
        existing,
        {"genicam_nodes": {"PixelFormat": "RGB8"}},
        nested_merge_keys=("genicam_nodes",),
    )

    assert existing == {"genicam_nodes": {"PixelFormat": "RGB8", "ReverseX": False}}


def test_merge_configure_settings_replaces_dicts_not_listed_for_nested_merge():
    existing = {"focus_config": {"mode": "auto", "accuracy": "Normal"}, "genicam_nodes": {"PixelFormat": "Mono8"}}

    merge_configure_settings(
        existing,
        {"focus_config": {"mode": "manual"}, "genicam_nodes": {"ReverseX": True}},
    )

    assert existing == {
        "focus_config": {"mode": "manual"},
        "genicam_nodes": {"ReverseX": True},
    }


def test_applied_subset_from_exception_reads_details_applied():
    from mindtrace.hardware.core.exceptions import CameraConfigurationError

    exc = CameraConfigurationError("partial", details={"applied": {"PixelFormat": "Mono8"}})
    assert applied_subset_from_exception(exc) == {"PixelFormat": "Mono8"}
    assert applied_subset_from_exception(CameraConfigurationError("none")) == {}
    assert applied_subset_from_exception(RuntimeError("plain")) == {}


def test_find_skipped_keys_reports_unknown_top_level_keys():
    data = {
        "camera_type": "basler",
        "timestamp": 1.0,
        "exposure": 12000.0,
        "triggermode": "trigger",
    }

    assert find_skipped_keys(data) == ("camera_type", "timestamp")


def test_find_skipped_keys_reports_unknown_nested_settings_keys():
    data = {
        "camera_type": "basler",
        "settings": {
            "exposure": 12000.0,
            "unknown_flag": True,
        },
    }

    assert find_skipped_keys(data) == ("camera_type", "unknown_flag")


def test_find_skipped_keys_treats_legacy_aliases_as_consumed():
    data = {
        "exposure": 12000.0,
        "triggermode": "trigger",
        "img_quality_enhancement": True,
        "roi_x": 1,
        "roi_y": 2,
        "width": 640,
        "height": 480,
    }

    assert find_skipped_keys(data) == ()


def test_parse_configure_settings_rejects_malformed_roi():
    normalized, invalid = parse_configure_settings({"roi": "full", "gain": 2.0})

    assert normalized == {"gain": 2.0}
    assert "roi" in invalid
    assert "roi" not in normalized
    assert normalize_settings({"roi": "full"}) == {}


def test_parse_configure_settings_rejects_incomplete_roi_dict():
    normalized, invalid = parse_configure_settings({"roi": {"x": 10}})

    assert "roi" not in normalized
    assert "missing keys" in invalid["roi"]


def test_parse_configure_settings_rejects_roi_with_wrong_length():
    _, invalid = parse_configure_settings({"roi": [1, 2, 3]})

    assert "roi" in invalid


def test_find_skipped_keys_treats_malformed_roi_as_consumed():
    assert find_skipped_keys({"roi": "full", "gain": 2.0}) == ()
