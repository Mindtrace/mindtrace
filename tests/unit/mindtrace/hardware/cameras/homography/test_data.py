import json

import numpy as np

from mindtrace.hardware.cameras.homography.data import CalibrationData, MeasuredBox


def test_calibration_data_save_and_load_roundtrip(tmp_path):
    filepath = tmp_path / "nested" / "calibration.json"
    original = CalibrationData(
        H=np.eye(3),
        camera_matrix=np.array([[1.0, 0, 2.0], [0, 1.0, 3.0], [0, 0, 1.0]]),
        dist_coeffs=np.array([0.1, 0.2, 0.3]),
        world_unit="cm",
        plane_normal_camera=np.array([0.0, 0.0, 1.0]),
    )

    original.save(str(filepath))
    assert filepath.exists()

    loaded = CalibrationData.load(str(filepath))
    assert np.array_equal(loaded.H, original.H)
    assert np.array_equal(loaded.camera_matrix, original.camera_matrix)
    assert np.array_equal(loaded.dist_coeffs, original.dist_coeffs)
    assert np.array_equal(loaded.plane_normal_camera, original.plane_normal_camera)
    assert loaded.world_unit == "cm"


def test_calibration_data_load_defaults_world_unit(tmp_path):
    filepath = tmp_path / "calibration.json"
    filepath.write_text(json.dumps({"H": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}))

    loaded = CalibrationData.load(str(filepath))
    assert loaded.world_unit == "mm"
    assert loaded.camera_matrix is None
    assert loaded.dist_coeffs is None
    assert loaded.plane_normal_camera is None


def test_measured_box_to_dict_serializes_corners():
    measured = MeasuredBox(
        corners_world=np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]]),
        width_world=2.0,
        height_world=1.0,
        area_world=2.0,
        unit="m",
    )

    as_dict = measured.to_dict()
    assert as_dict["corners_world"] == [[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]]
    assert as_dict["width_world"] == 2.0
    assert as_dict["height_world"] == 1.0
    assert as_dict["area_world"] == 2.0
    assert as_dict["unit"] == "m"
