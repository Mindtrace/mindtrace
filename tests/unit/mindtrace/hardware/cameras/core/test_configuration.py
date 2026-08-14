"""Tests for canonical camera configuration normalization."""

from mindtrace.hardware.cameras.core.configuration import (
    ConfigurationApplyResult,
    find_skipped_keys,
    normalize_settings,
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


def test_settings_to_camera_configuration_dict_filters_api_fields():
    data = {
        "exposure_time": 1000.0,
        "focus_config": {"mode": "auto"},
        "genicam_nodes": {"PixelFormat": "Mono8"},
        "brightness": 0.5,
    }

    mapped = settings_to_camera_configuration_dict(data)

    assert mapped["exposure_time"] == 1000.0
    assert "focus_config" not in mapped
    assert "genicam_nodes" not in mapped
    assert "brightness" not in mapped


def test_configuration_apply_result_success_property():
    assert ConfigurationApplyResult(applied=3, total=3).success is True
    assert ConfigurationApplyResult(applied=0, total=0).success is True
    assert ConfigurationApplyResult(applied=2, total=5).success is False
    assert ConfigurationApplyResult(applied=0, total=0, skipped=("exposre_time",)).success is False
    assert ConfigurationApplyResult(applied=1, total=1, skipped=("camera_type",)).success is True


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
