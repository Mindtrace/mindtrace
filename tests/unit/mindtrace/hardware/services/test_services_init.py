"""Tests for lazy imports in mindtrace.hardware.services."""

import importlib
import sys
import types

import pytest


@pytest.fixture
def services_module():
    import mindtrace.hardware.services as services

    return importlib.reload(services)


def test_getattr_camera_service_branch(monkeypatch, services_module):
    fake = types.ModuleType("mindtrace.hardware.services.cameras")
    fake.CameraManagerService = object()
    fake.CameraManagerConnectionManager = object()
    monkeypatch.setitem(sys.modules, "mindtrace.hardware.services.cameras", fake)

    assert services_module.__getattr__("CameraManagerService") is fake.CameraManagerService
    assert services_module.__getattr__("CameraManagerConnectionManager") is fake.CameraManagerConnectionManager


def test_getattr_sensor_service_branch(monkeypatch, services_module):
    fake = types.ModuleType("mindtrace.hardware.services.sensors")
    fake.SensorManagerService = object()
    fake.SensorConnectionManager = object()
    monkeypatch.setitem(sys.modules, "mindtrace.hardware.services.sensors", fake)

    assert services_module.__getattr__("SensorManagerService") is fake.SensorManagerService
    assert services_module.__getattr__("SensorConnectionManager") is fake.SensorConnectionManager


def test_getattr_unknown_attr_raises(services_module):
    with pytest.raises(AttributeError):
        services_module.__getattr__("DefinitelyMissing")
