from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import Registry, Store
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
)


@pytest.fixture
def two_mount_store():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        r1 = Registry(backend=d1, version_objects=True, mutable=True)
        r2 = Registry(backend=d2, version_objects=True, mutable=True)
        yield Store(mounts={"a": r1, "b": r2}, default_location="a")


def test_store_default_mount_uses_config_store_dir():
    store = Store()
    assert store.default_location == "default"
    mount = store.get_mount("default")
    expected = Path(store.config["MINDTRACE_DIR_PATHS"]["STORE_DIR"]).expanduser().resolve()
    assert mount.registry.backend.uri == expected


def test_save_requires_qualified_key(two_mount_store):
    with pytest.raises(StoreKeyFormatError):
        two_mount_store.save("my_obj", 1)


def test_delete_requires_qualified_key(two_mount_store):
    with pytest.raises(StoreKeyFormatError):
        two_mount_store.delete("my_obj")


def test_qualified_save_and_load(two_mount_store):
    two_mount_store.save("a/obj1", {"x": 1})
    assert two_mount_store.load("a/obj1") == {"x": 1}


def test_unqualified_load_discovers_object(two_mount_store):
    two_mount_store.save("a/obj1", "hello")
    assert two_mount_store.load("obj1") == "hello"


def test_unqualified_load_not_found(two_mount_store):
    with pytest.raises(RegistryObjectNotFound):
        two_mount_store.load("missing")


def test_unqualified_load_ambiguous(two_mount_store):
    two_mount_store.save("a/same", 1)
    two_mount_store.save("b/same", 2)
    with pytest.raises(StoreAmbiguousObjectError):
        two_mount_store.load("same")


def test_cache_updates_on_discovered_load(two_mount_store):
    two_mount_store.save("b/name1", "v")
    assert two_mount_store.cache_lookup_locations("name1") == ["b"]
    assert two_mount_store.load("name1") == "v"
    assert two_mount_store.cache_lookup_locations("name1")[0] == "b"


def test_has_object_qualified_and_unqualified(two_mount_store):
    two_mount_store.save("a/obj", 9)
    assert two_mount_store.has_object("a/obj")
    assert two_mount_store.has_object("obj")
    assert not two_mount_store.has_object("missing")


def test_list_objects_and_versions(two_mount_store):
    two_mount_store.save("a/obj", 1)
    two_mount_store.save("a/obj", 2)
    keys = two_mount_store.list_objects()
    assert "a/obj" in keys

    versions = two_mount_store.list_versions("a/obj")
    assert versions == ["1.0.0", "1.0.1"]


def test_info_for_unqualified_name_uses_discovery(two_mount_store):
    two_mount_store.save("a/info:obj", {"k": 1})
    payload = two_mount_store.info("info:obj")
    assert payload
