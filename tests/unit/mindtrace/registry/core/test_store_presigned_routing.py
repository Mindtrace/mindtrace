"""Presigned single-object reads use Store discovery without loading payloads."""

from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry, Store
from mindtrace.registry.core.exceptions import RegistryObjectNotFound, StoreAmbiguousObjectError


def test_discovers_remote_owner(tmp_path, cached_mock_registry):
    local = Registry(backend=tmp_path / "local", version_objects=True)
    remote = cached_mock_registry
    remote.save("item", b"payload", version="1.0.0")
    store = Store(mounts={"local": local, "remote": remote}, default_mount="local")

    expected = store.create_direct_download_url("remote/item", version="1.0.0")
    assert expected.startswith("https://example.invalid/")
    assert store.create_direct_download_url("item", version="1.0.0") == expected


def test_rejects_ambiguous_read(tmp_path, cached_mock_registry):
    local = Registry(backend=tmp_path / "local", version_objects=True)
    remote = cached_mock_registry
    for registry in (local, remote):
        registry.save("item", b"payload", version="1.0.0")
    store = Store(mounts={"local": local, "remote": remote}, default_mount="remote")

    with pytest.raises(StoreAmbiguousObjectError):
        store.create_direct_download_url("item", version="1.0.0")


def test_reports_no_unqualified_match(tmp_path):
    local = Registry(backend=tmp_path / "local", version_objects=True)
    store = Store(mounts={"local": local}, default_mount="local")

    with pytest.raises(RegistryObjectNotFound):
        store.create_direct_download_url("missing", version="1.0.0")


@pytest.fixture
def download_store(tmp_path, cached_mock_registry):
    local = Registry(backend=tmp_path / "local", version_objects=True)
    store = Store(mounts={"local": local}, default_mount="local")
    store.add_mount(cached_mock_registry, name="remote", read_only=True)
    return store


@pytest.mark.parametrize(
    "key,version,expected_version",
    [
        ("models/item", None, "2.0.0"),
        ("models/item", "latest", "2.0.0"),
        ("models/item@1.0.0", None, "1.0.0"),
        ("models/item@1.0.0", "2.0.0", "2.0.0"),
        ("models/item@1.0.0", "latest", "2.0.0"),
        ("models/item", "1", "1.0.0"),
    ],
)
def test_preserves_version_selection_and_url_options(download_store, monkeypatch, key, version, expected_version):
    store = download_store
    remote = store.get_mount("remote").registry
    remote.save("models/item", b"old", version="1.0.0")
    remote.save("models/item", b"new", version="2.0.0")
    options = {
        "expiration_minutes": 7,
        "response_content_type": "application/custom",
        "response_content_disposition": "attachment",
        "filename": "data.txt",
    }
    expected = remote.create_direct_download_url("models/item", expected_version, **options)
    presign = Mock(wraps=remote._remote.backend.create_direct_download_url)
    monkeypatch.setattr(remote._remote.backend, "create_direct_download_url", presign)
    load = Mock(side_effect=AssertionError("Signing must not load the payload"))
    monkeypatch.setattr(remote, "load", load)

    assert store.create_direct_download_url(key, version=version, **options) == expected
    presign.assert_called_once_with("models/item", expected_version, **options)
    load.assert_not_called()


@pytest.mark.parametrize("key,version", [("item@2.0.0", None), ("item@1.0.0", "2.0.0")])
def test_discovery_filters_by_effective_version(download_store, key, version):
    store = download_store
    local = store.get_mount("local").registry
    remote = store.get_mount("remote").registry
    local.save("item", b"local", version="1.0.0")
    remote.save("item", b"remote", version="2.0.0")

    expected = remote.create_direct_download_url("item", "2.0.0")
    assert store.create_direct_download_url(key, version=version) == expected


@pytest.mark.parametrize("cache_enabled", [False, True])
def test_discovery_checks_each_mount_once_and_rechecks_cached_locations(download_store, monkeypatch, cache_enabled):
    store = download_store
    store._enable_location_cache = cache_enabled
    remote = store.get_mount("remote").registry
    remote.save("item", b"remote", version="1.0.0")
    checks = {}
    signers = {}
    for name in store.list_mounts():
        registry = store.get_mount(name).registry
        checks[name] = Mock(wraps=registry.has_object)
        signers[name] = Mock(wraps=registry.create_direct_download_url)
        monkeypatch.setattr(registry, "has_object", checks[name])
        monkeypatch.setattr(registry, "create_direct_download_url", signers[name])

    assert store.create_direct_download_url("item", version="1.0.0").startswith("https://example.invalid/")
    for check in checks.values():
        check.assert_called_once_with("item", "1.0.0")
        check.reset_mock()
    signers["remote"].assert_called_once()
    signers["local"].assert_not_called()
    signers["temp"].assert_not_called()
    for signer in signers.values():
        signer.reset_mock()

    # A warmed location cache is only an ordering hint, not permission to skip ambiguity checks.
    store.get_mount("local").registry.save("item", b"new local match", version="1.0.0")
    with pytest.raises(StoreAmbiguousObjectError):
        store.create_direct_download_url("item", version="1.0.0")
    for check in checks.values():
        check.assert_called_once_with("item", "1.0.0")
    for signer in signers.values():
        signer.assert_not_called()


@pytest.mark.parametrize("version", [None, "1.0.0"])
def test_qualified_signing_bypasses_discovery_even_with_duplicate_names(download_store, monkeypatch, version):
    store = download_store
    remote = store.get_mount("remote").registry
    remote.save("item", b"remote", version="1.0.0")
    store.get_mount("local").registry.save("item", b"local", version="1.0.0")
    expected = remote.create_direct_download_url("item", version)
    discover = Mock(side_effect=AssertionError("Qualified requests must not discover"))
    monkeypatch.setattr(store, "_resolve_load_location", discover)
    checks = []
    for name in store.list_mounts():
        check = Mock(side_effect=AssertionError("Qualified requests must not add existence checks"))
        monkeypatch.setattr(store.get_mount(name).registry, "has_object", check)
        checks.append(check)

    assert store.create_direct_download_url("remote/item", version=version) == expected
    discover.assert_not_called()
    for check in checks:
        check.assert_not_called()


def test_unique_local_owner_keeps_unsupported_capability_result(download_store, monkeypatch):
    store = download_store
    local = store.get_mount("local").registry
    local.save("item", b"local", version="1.0.0")
    store.set_default_mount("remote")
    presign = Mock(wraps=local.create_direct_download_url)
    monkeypatch.setattr(local, "create_direct_download_url", presign)

    assert store.create_direct_download_url("item", version="1.0.0") is None
    presign.assert_called_once()


@pytest.mark.parametrize("version", [None, "1.0.0"])
def test_no_match_does_not_issue_any_url(download_store, monkeypatch, version):
    store = download_store
    signers = []
    for name in store.list_mounts():
        signer = Mock(side_effect=AssertionError("Missing objects must not reach a signer"))
        monkeypatch.setattr(store.get_mount(name).registry, "create_direct_download_url", signer)
        signers.append(signer)

    with pytest.raises(RegistryObjectNotFound):
        store.create_direct_download_url("missing", version=version)
    for signer in signers:
        signer.assert_not_called()


def test_selected_signer_error_propagates_without_default_fallback(download_store, monkeypatch):
    store = download_store
    remote = store.get_mount("remote").registry
    remote.save("item", b"remote", version="1.0.0")
    error = PermissionError("Signing denied")
    signer = Mock(side_effect=error)
    fallback = Mock(side_effect=AssertionError("No default fallback after a signing error"))
    monkeypatch.setattr(remote, "create_direct_download_url", signer)
    monkeypatch.setattr(store.get_mount("local").registry, "create_direct_download_url", fallback)

    with pytest.raises(PermissionError) as exc:
        store.create_direct_download_url("item", version="1.0.0")
    assert exc.value is error
    signer.assert_called_once()
    fallback.assert_not_called()
