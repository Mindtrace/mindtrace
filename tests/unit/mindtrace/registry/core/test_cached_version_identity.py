"""Single cached reads must retain one concrete source version."""

import json
from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry, S3RegistryBackend
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from tests.registry_test_helpers import RevisionedIntMaterializer


@pytest.mark.parametrize("version", [None, "latest"])
def test_cached_read_pins_version_before_remote_load(cached_mock_registry, monkeypatch, version):
    reader = cached_mock_registry
    writer = Registry(backend=reader.backend, use_cache=False)
    writer.save("item", 1, version="1.0.0")
    monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
    original_load = reader._remote.load
    published = []

    def publish_then_load(*args, **kwargs):
        if not published:
            writer.save("item", 2, version="2.0.0")
            published.append("2.0.0")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(reader._remote, "load", publish_then_load)
    value = reader.load("item", version, verify="full")
    assert published == ["2.0.0"]
    assert value == 1  # The version selected before remote loading.
    assert reader._cache.load("item", "1.0.0") == writer.load("item", "1.0.0")
    assert reader.load("item", "1.0.0", verify="none") == 1
    assert writer.load("item", "2.0.0") == 2


@pytest.mark.parametrize("version", [None, "latest", "1.0.0"])
@pytest.mark.parametrize("verify", ["none", "integrity", "full"])
@pytest.mark.parametrize("warm", [False, True])
def test_cached_read_backend_call_budget(cached_mock_registry, monkeypatch, record_property, version, verify, warm):
    reader = cached_mock_registry
    reader._remote.save("item", 7, version="1.0.0")
    if warm:
        reader._cache.save("item", 7, version="1.0.0")
    monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
    calls = {}
    for method in ("list_versions", "fetch_metadata", "pull"):
        calls[method] = Mock(wraps=getattr(reader.backend, method))
        monkeypatch.setattr(reader.backend, method, calls[method])
    exists = Mock(wraps=reader._remote.has_object)
    monkeypatch.setattr(reader._remote, "has_object", exists)

    assert reader.load("item", version, verify=verify) == 7
    observed = {method: call.call_count for method, call in calls.items()}
    record_property("remote_calls", json.dumps(observed, sort_keys=True))
    # Existing request budgets; pinning must not add I/O to any path.
    listing_budget = (1 if warm else 2) if version in (None, "latest") else 0
    assert observed["list_versions"] <= listing_budget
    assert observed["fetch_metadata"] == (1 if not warm or verify == "full" else 0)
    assert observed["pull"] == (0 if warm else 1)
    exists.assert_not_called()


@pytest.mark.parametrize("version", ["1", "1.0", "1.0.0"])
def test_explicit_versions_keep_normalized_cache_identity(cached_mock_registry, monkeypatch, version):
    reader = cached_mock_registry
    reader._remote.save("item", 1, version="1.0.0")
    reader._remote.save("item", 2, version="2.0.0")
    load = Mock(wraps=reader._remote.load)
    monkeypatch.setattr(reader._remote, "load", load)

    assert reader.load("item", version, verify="full") == 1
    assert reader._cache.list_versions("item") == ["1.0.0"]
    load.reset_mock()
    assert reader.load("item", version, verify="none") == 1
    load.assert_not_called()


@pytest.mark.parametrize("version", [None, "latest", "1.0.0"])
def test_unversioned_reads_remain_supported(cached_mock_registry, tmp_path, version):
    # The shared fixture installs the mock transport; use a separate unversioned backend.
    backend = S3RegistryBackend(
        uri=tmp_path / "unversioned",
        endpoint="example.invalid",
        access_key="test",
        secret_key="test",
        bucket="unversioned-contract-tests",
        secure=False,
    )
    reader = Registry(backend=backend, version_objects=False, use_cache=True)
    reader._remote.save("item", 7)
    assert reader.load("item", version) == 7
    assert reader._cache.list_versions("item") == ["1.0.0"]
    assert reader.load("item", version, verify="none") == 7


@pytest.mark.parametrize(
    "version,error_type", [(None, RegistryObjectNotFound), ("latest", RegistryObjectNotFound), ("bad", ValueError)]
)
def test_resolution_failures_do_not_publish_cache(cached_mock_registry, monkeypatch, version, error_type):
    reader = cached_mock_registry
    save = Mock(wraps=reader._cache.save)
    monkeypatch.setattr(reader._cache, "save", save)
    with pytest.raises(error_type):
        reader.load("missing", version)
    save.assert_not_called()


def test_deleted_pinned_version_is_not_replaced_by_a_newer_one(cached_mock_registry, monkeypatch):
    reader = cached_mock_registry
    writer = Registry(backend=reader.backend, use_cache=False)
    writer.save("item", 1, version="1.0.0")
    monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
    original_load = reader._remote.load

    def replace_then_load(*args, **kwargs):
        writer.save("item", 2, version="2.0.0")
        writer.delete("item", "1.0.0")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(reader._remote, "load", replace_then_load)
    save = Mock(wraps=reader._cache.save)
    monkeypatch.setattr(reader._cache, "save", save)
    with pytest.raises(RegistryObjectNotFound):
        reader.load("item", "latest")
    save.assert_not_called()
    assert writer.load("item", "2.0.0") == 2


def test_remote_error_is_preserved_without_cache_publication(cached_mock_registry, monkeypatch):
    reader = cached_mock_registry
    reader._remote.save("item", 1, version="1.0.0")
    error = PermissionError("source unavailable")
    monkeypatch.setattr(reader._remote, "load", Mock(side_effect=error))
    save = Mock(wraps=reader._cache.save)
    monkeypatch.setattr(reader._cache, "save", save)
    with pytest.raises(PermissionError) as exc:
        reader.load("item")
    assert exc.value is error
    save.assert_not_called()


def test_remote_load_options_and_best_effort_cache_failure(cached_mock_registry, monkeypatch, tmp_path):
    reader = cached_mock_registry
    reader._remote.register_materializer(int, RevisionedIntMaterializer)
    reader._remote.save("item", 7, version="1.0.0")
    load = Mock(wraps=reader._remote.load)
    monkeypatch.setattr(reader._remote, "load", load)
    save = Mock(side_effect=OSError("cache full"))
    monkeypatch.setattr(reader._cache, "save", save)
    output = str(tmp_path / "output")

    assert reader.load("item", "latest", output_dir=output, verify="none", offset=3) == 10
    load.assert_called_once_with("item", "1.0.0", output_dir=output, verify="none", offset=3)
    save.assert_called_once()
    assert save.call_args.kwargs["version"] == "1.0.0"


def test_batch_already_uses_concrete_versions(cached_mock_registry, monkeypatch):
    reader = cached_mock_registry
    writer = Registry(backend=reader.backend, use_cache=False)
    writer.save("item", 1, version="1.0.0")
    monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
    original_load = reader._remote.load

    def publish_then_load(*args, **kwargs):
        writer.save("item", 2, version="2.0.0")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(reader._remote, "load", publish_then_load)
    result = reader.load(["item"], ["latest"])
    assert result.results == [1]
    assert result.failure_count == 0
    assert reader._cache.load("item", "1.0.0") == 1
