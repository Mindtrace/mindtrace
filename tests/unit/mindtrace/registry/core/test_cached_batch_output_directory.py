"""Cached batch reads must honor Path output placement without extra remote I/O."""

import json
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("warm_count", [0, 1, 2])
def test_cached_batch_output_directory(cached_mock_registry, tmp_path, warm_count):
    registry = cached_mock_registry
    names = ["first", "second"]
    for name, text in zip(names, ["A", "B"]):
        source = tmp_path / f"{name}.txt"
        source.write_text(text, encoding="utf-8")
        registry._remote.save(name, source, version="1.0.0")

    for name in names[:warm_count]:
        registry._cache.download(registry._remote, name, version="1.0.0", target_version="1.0.0")

    output = tmp_path / "export"
    result = registry.load(names, ["1.0.0", "1.0.0"], output_dir=str(output))

    assert result.succeeded == [(name, "1.0.0") for name in names]
    assert result.failed == []
    assert result.errors == {}
    assert [path.read_text(encoding="utf-8") for path in result.results] == ["A", "B"]
    assert all(path.resolve().is_relative_to(output.resolve()) for path in result.results)


@pytest.mark.parametrize("warm_count", [0, 1, 2])
@pytest.mark.parametrize("verify", ["none", "integrity", "full"])
def test_directory_output_preserves_cache_and_remote_call_budget(
    cached_mock_registry, tmp_path, monkeypatch, record_property, warm_count, verify
):
    registry = cached_mock_registry
    # Identical basenames remain separate under the existing per-object output layout.
    names = ["first", "nested/second"]
    for index, name in enumerate(names):
        source = tmp_path / f"source-{index}"
        (source / "nested").mkdir(parents=True)
        (source / "nested" / "data.txt").write_text(str(index), encoding="utf-8")
        registry._remote.save(name, source, version="1.0.0")
    for name in names[:warm_count]:
        registry._cache.download(registry._remote, name, version="1.0.0", target_version="1.0.0")

    calls = {}
    for method in ("list_versions", "fetch_metadata", "pull"):
        calls[method] = Mock(wraps=getattr(registry.backend, method))
        monkeypatch.setattr(registry.backend, method, calls[method])
    remote_load = Mock(wraps=registry._remote.load)
    monkeypatch.setattr(registry._remote, "load", remote_load)

    output = tmp_path / "new" / "export"
    result = registry.load(names, "1.0.0", output_dir=str(output), verify=verify)
    record_property("remote_calls", json.dumps({name: call.call_count for name, call in calls.items()}, sort_keys=True))
    assert result.succeeded == [(name, "1.0.0") for name in names]
    assert result.failed == []
    assert result.errors == {}
    assert [(path / "nested" / "data.txt").read_text(encoding="utf-8") for path in result.results] == ["0", "1"]
    if warm_count == 2:
        remote_load.assert_not_called()
        calls["pull"].assert_not_called()
    else:
        remote_load.assert_called_once_with(
            names[warm_count:], ["1.0.0"] * (2 - warm_count), output_dir=str(output), verify=verify
        )

    # Export moves materialized copies, not committed cache artifacts.
    remote_load.reset_mock()
    again = registry.load(names, "1.0.0", verify="none")
    assert again.failure_count == 0, again.errors
    assert [(path / "nested" / "data.txt").read_text(encoding="utf-8") for path in again.results] == ["0", "1"]
    remote_load.assert_not_called()
    assert all(path.resolve().is_relative_to(output.resolve()) for path in result.results)


def test_omitted_output_directory_keeps_readable_file_paths(cached_mock_registry, tmp_path):
    registry = cached_mock_registry
    source = tmp_path / "source.txt"
    source.write_text("unchanged", encoding="utf-8")
    registry.save("warm", source, version="1.0.0")
    registry._remote.save("cold", source, version="1.0.0")
    result = registry.load(["warm", "cold"], "1.0.0", verify="none")
    assert result.failure_count == 0, result.errors
    assert [path.read_text(encoding="utf-8") for path in result.results] == ["unchanged", "unchanged"]


def test_output_directory_preserves_non_path_values_and_missing_item_errors(cached_mock_registry, tmp_path):
    registry = cached_mock_registry
    registry.save("warm", 1, version="1.0.0")
    registry._remote.save("cold", 2, version="1.0.0")
    output = tmp_path / "export"
    result = registry.load(["warm", "missing", "cold"], "1.0.0", output_dir=str(output))
    assert result.results == [1, None, 2]
    assert result.succeeded == [("warm", "1.0.0"), ("cold", "1.0.0")]
    assert result.failed == [("missing", "1.0.0")]
    assert result.errors[("missing", "1.0.0")]["error"] == "RegistryObjectNotFound"
    assert not output.exists()
