"""Cached batch success must not depend on whether the loaded value is None."""

import json
from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry
from mindtrace.registry.archivers.builtin_materializers import BuiltInMaterializer
from tests.registry_test_helpers import FailingLoadMaterializer


@pytest.mark.parametrize("warm", [False, True])
@pytest.mark.parametrize("verify", ["none", "integrity", "full"])
def test_saved_none_keeps_batch_success_and_remote_call_budget(
    cached_mock_registry, monkeypatch, record_property, warm, verify
):
    registry = cached_mock_registry
    registry._remote.save("item", None, version="1.0.0", materializer=BuiltInMaterializer)
    if warm:
        registry._cache.save("item", None, version="1.0.0", materializer=BuiltInMaterializer)

    # Same stored value succeeds without the cache wrapper and as a scalar.
    direct = Registry(backend=registry.backend, use_cache=False)
    control = direct.load(["item"], "1.0.0", verify=verify)
    assert control.results == [None]
    assert control.succeeded == [("item", "1.0.0")]
    assert control.errors == {}
    assert registry.load("item", "1.0.0", verify=verify) is None

    calls = {}
    for method in ("list_versions", "fetch_metadata", "pull"):
        calls[method] = Mock(wraps=getattr(registry.backend, method))
        monkeypatch.setattr(registry.backend, method, calls[method])
    remote_load = Mock(wraps=registry._remote.load)
    cache_save = Mock(wraps=registry._cache.save)
    touch = Mock(wraps=registry._touch_cache_entry)
    monkeypatch.setattr(registry._remote, "load", remote_load)
    monkeypatch.setattr(registry._cache, "save", cache_save)
    monkeypatch.setattr(registry, "_touch_cache_entry", touch)

    result = registry.load(["item"], "1.0.0", verify=verify)
    record_property("remote_calls", json.dumps({name: call.call_count for name, call in calls.items()}, sort_keys=True))
    assert result.results == [None]
    assert result.succeeded == [("item", "1.0.0")]
    assert result.failed == []
    assert result.errors == {}
    if warm:
        remote_load.assert_not_called()
        calls["pull"].assert_not_called()
        touch.assert_called_once_with("item", "1.0.0")
    else:
        remote_load.assert_called_once_with(["item"], ["1.0.0"], output_dir=None, verify=verify)
    # Preserve the existing cache-fill policy; serialization is a separate scope.
    cache_save.assert_not_called()


def test_mixed_none_values_and_real_errors_survive_cache_write_failure(cached_mock_registry, monkeypatch):
    registry = cached_mock_registry
    for name in ("warm", "cold"):
        registry._remote.save(name, None, version="1.0.0", materializer=BuiltInMaterializer)
    registry._cache.save("warm", None, version="1.0.0", materializer=BuiltInMaterializer)
    registry._remote.save("zero", 0, version="1.0.0")
    registry._remote.save("bad", 1, version="1.0.0", materializer=FailingLoadMaterializer)
    remote_load = Mock(wraps=registry._remote.load)
    write = Mock(side_effect=OSError("cache disk full"))
    monkeypatch.setattr(registry._remote, "load", remote_load)
    monkeypatch.setattr(registry._cache.backend, "push", write)

    result = registry.load(["bad", "warm", "missing", "zero", "cold"], "1.0.0", verify="none")

    assert result.results == [None, None, None, 0, None]
    assert result.succeeded == [("warm", "1.0.0"), ("zero", "1.0.0"), ("cold", "1.0.0")]
    assert result.failed == [("bad", "1.0.0"), ("missing", "1.0.0")]
    assert set(result.errors) == {("bad", "1.0.0"), ("missing", "1.0.0")}
    assert result.errors[("bad", "1.0.0")] == {
        "error": "ValueError",
        "message": "test materializer cannot decode this artifact",
    }
    assert result.errors[("missing", "1.0.0")]["error"] == "RegistryObjectNotFound"
    remote_load.assert_called_once_with(
        ["bad", "missing", "zero", "cold"], ["1.0.0"] * 4, output_dir=None, verify="none"
    )
    write.assert_called_once()


@pytest.mark.parametrize("cached_value,remote_value", [(None, 7), (7, None)])
def test_full_verification_refreshes_stale_none_in_either_direction(
    cached_mock_registry, monkeypatch, cached_value, remote_value
):
    registry = cached_mock_registry
    registry._remote.save("item", remote_value, version="1.0.0", materializer=BuiltInMaterializer)
    registry._cache.save("item", cached_value, version="1.0.0", materializer=BuiltInMaterializer)
    remote_load = Mock(wraps=registry._remote.load)
    stale = Mock(wraps=registry._find_stale_indices)
    monkeypatch.setattr(registry._remote, "load", remote_load)
    monkeypatch.setattr(registry, "_find_stale_indices", stale)

    result = registry.load(["item"], "1.0.0", verify="full")

    assert result.results == [remote_value]
    assert result.succeeded == [("item", "1.0.0")]
    assert result.failed == []
    assert result.errors == {}
    stale.assert_called_once_with([("item", "1.0.0")], [0])
    remote_load.assert_called_once_with(["item"], ["1.0.0"], output_dir=None, verify="full")


def test_cache_materializer_error_falls_back_to_successful_remote_none(cached_mock_registry, monkeypatch):
    registry = cached_mock_registry
    registry._remote.save("item", None, version="1.0.0", materializer=BuiltInMaterializer)
    registry._cache.save("item", 1, version="1.0.0", materializer=FailingLoadMaterializer)
    remote_load = Mock(wraps=registry._remote.load)
    monkeypatch.setattr(registry._remote, "load", remote_load)

    result = registry.load(["item"], "1.0.0", verify="integrity")

    assert result.results == [None]
    assert result.succeeded == [("item", "1.0.0")]
    assert result.failed == []
    assert result.errors == {}
    remote_load.assert_called_once_with(["item"], ["1.0.0"], output_dir=None, verify="integrity")
