from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import Registry, Store
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
    StoreLocationNotFound,
)


@pytest.fixture
def two_mount_store():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        r1 = Registry(backend=d1, version_objects=True, mutable=True)
        r2 = Registry(backend=d2, version_objects=True, mutable=True)
        yield Store(mounts={"a": r1, "b": r2}, default_mount="a")


def test_store_always_has_temp_mount_uses_temp_dir():
    store = Store()
    assert store.default_mount == "temp"
    mount = store.get_mount("temp")
    assert mount.registry.backend.uri.exists()
    assert mount.registry.backend.uri.name.startswith("mindtrace-store-")


def test_store_requires_configured_default_mount():
    with pytest.raises(StoreLocationNotFound):
        Store(default_mount="missing")


def test_add_mount_invalid_name_raises(two_mount_store):
    with TemporaryDirectory() as d:
        registry = Registry(backend=d, version_objects=True, mutable=True)
        with pytest.raises(ValueError):
            two_mount_store.add_mount("", registry)
        with pytest.raises(ValueError):
            two_mount_store.add_mount("bad/name", registry)
        with pytest.raises(ValueError):
            two_mount_store.add_mount("bad@name", registry)



def test_add_mount_duplicate_raises(two_mount_store):
    with TemporaryDirectory() as d:
        registry = Registry(backend=d, version_objects=True, mutable=True)
        with pytest.raises(ValueError):
            two_mount_store.add_mount("a", registry)



def test_set_default_mount_updates_default(two_mount_store):
    two_mount_store.set_default_mount("b")
    assert two_mount_store.default_mount == "b"


def test_get_registry_returns_mount_registry(two_mount_store):
    assert two_mount_store.get_registry("a") is two_mount_store.get_mount("a").registry
    assert two_mount_store.get_registry("a/example:item") is two_mount_store.get_mount("a").registry



def test_get_mount_missing_raises(two_mount_store):
    with pytest.raises(StoreLocationNotFound):
        two_mount_store.get_mount("missing")



def test_unqualified_save_uses_default_mount(two_mount_store):
    two_mount_store.save("my:obj", 1)
    assert two_mount_store.load("a/my:obj") == 1


def test_unqualified_delete_uses_default_mount(two_mount_store):
    two_mount_store.save("my:obj", 1)
    two_mount_store.delete("my:obj")
    with pytest.raises(RegistryObjectNotFound):
        two_mount_store.load("a/my:obj")


def test_qualified_save_and_load(two_mount_store):
    two_mount_store.save("a/obj1", {"x": 1})
    assert two_mount_store.load("a/obj1") == {"x": 1}


def test_unqualified_load_discovers_object(two_mount_store):
    two_mount_store.save("a/obj1", "hello")
    assert two_mount_store.load("obj1") == "hello"



def test_parse_key_invalid_forms(two_mount_store):
    with pytest.raises(StoreKeyFormatError):
        two_mount_store.parse_key("@1.0.0")
    with pytest.raises(StoreKeyFormatError):
        two_mount_store.parse_key("a/")



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



def test_cache_disabled_noops():
    with TemporaryDirectory() as d:
        registry = Registry(backend=d, version_objects=True, mutable=True)
        store = Store(mounts={"a": registry}, default_mount="a", enable_location_cache=False)
        store.cache_update_location("name1", "a")
        assert store.cache_lookup_locations("name1") == []



def test_has_object_qualified_and_unqualified(two_mount_store):
    two_mount_store.save("a/obj", 9)
    assert two_mount_store.has_object("a/obj")
    assert two_mount_store.has_object("obj")
    assert not two_mount_store.has_object("missing")


def test_list_objects_and_versions(two_mount_store):
    two_mount_store.save("a/obj", 1)
    two_mount_store.save("a/obj", 2)
    two_mount_store.save("b/other", 3)
    keys = two_mount_store.list_objects()
    assert "a/obj" in keys
    assert "temp" in two_mount_store.list_mounts()

    versions = two_mount_store.list_versions("a/obj")
    assert versions == ["1.0.0", "1.0.1"]

    scoped = two_mount_store.list_objects_and_versions("a")
    assert scoped["a/obj"] == ["1.0.0", "1.0.1"]

    all_versions = two_mount_store.list_objects_and_versions()
    assert all_versions["a/obj"] == ["1.0.0", "1.0.1"]
    assert all_versions["b/other"] == ["1.0.0"]



def test_list_versions_requires_qualified_key(two_mount_store):
    with pytest.raises(StoreKeyFormatError):
        two_mount_store.list_versions("obj")



def test_info_for_unqualified_name_uses_discovery(two_mount_store):
    two_mount_store.save("a/info:obj", {"k": 1})
    payload = two_mount_store.info("info:obj")
    assert payload


def test_info_without_name_reports_default_mount(two_mount_store):
    payload = two_mount_store.info()
    assert payload["default_mount"] == "a"


def test_pop_unqualified_resolves_and_deletes(two_mount_store):
    two_mount_store.save("b/pop:item", {"v": 1})
    assert two_mount_store.pop("pop:item") == {"v": 1}
    with pytest.raises(RegistryObjectNotFound):
        two_mount_store.load("b/pop:item")


def test_pop_unqualified_ambiguous_raises(two_mount_store):
    two_mount_store.save("a/shared:item", 1)
    two_mount_store.save("b/shared:item", 2)
    with pytest.raises(StoreAmbiguousObjectError):
        two_mount_store.pop("shared:item")


def test_setdefault_unqualified_uses_default_mount(two_mount_store):
    assert two_mount_store.setdefault("new:item", {"ok": True}) == {"ok": True}
    assert two_mount_store.load("a/new:item") == {"ok": True}


def test_get_does_not_swallow_ambiguity(two_mount_store):
    two_mount_store.save("a/dup:item", 1)
    two_mount_store.save("b/dup:item", 2)
    with pytest.raises(StoreAmbiguousObjectError):
        two_mount_store.get("dup:item")


def test_remove_mount_evicts_location_cache(two_mount_store):
    two_mount_store.save("b/cache:item", "v")
    assert two_mount_store.load("cache:item") == "v"
    assert two_mount_store.cache_lookup_locations("cache:item") == ["b"]
    two_mount_store.remove_mount("b")
    assert two_mount_store.cache_lookup_locations("cache:item") == []



def test_remove_mount_missing_raises(two_mount_store):
    with pytest.raises(StoreLocationNotFound):
        two_mount_store.remove_mount("missing")



def test_remove_mount_retains_remaining_cache_entries(two_mount_store):
    two_mount_store.cache_update_location("shared:item", "a")
    two_mount_store.cache_update_location("shared:item", "b")
    two_mount_store.remove_mount("b")
    assert two_mount_store.cache_lookup_locations("shared:item") == ["a"]



def test_remove_mount_cannot_remove_temp(two_mount_store):
    with pytest.raises(ValueError):
        two_mount_store.remove_mount("temp")


def test_remove_default_mount_resets_to_temp(two_mount_store):
    two_mount_store.set_default_mount("b")
    two_mount_store.remove_mount("b")
    assert two_mount_store.default_mount == "temp"


def test_list_mount_info_includes_version_digits(two_mount_store):
    info = two_mount_store.list_mount_info()
    assert info["a"]["version_digits"] == two_mount_store.get_mount("a").registry.version_digits


def test_update_mapping_unqualified_uses_default_mount(two_mount_store):
    two_mount_store.update({"mapped:item": 5})
    assert two_mount_store.load("a/mapped:item") == 5


def test_update_store_sync_all_versions_copies_all_versions_to_default_mount():
    with TemporaryDirectory() as src1, TemporaryDirectory() as src2, TemporaryDirectory() as dst:
        source = Store(
            mounts={
                "a": Registry(backend=src1, version_objects=True, mutable=True),
                "b": Registry(backend=src2, version_objects=True, mutable=True),
            },
            default_mount="a",
        )
        target = Store(mounts={"temp": Registry(backend=dst, version_objects=True, mutable=True)})

        source.save("a/versioned:item", 1)
        source.save("a/versioned:item", 2)

        target.update(source, sync_all_versions=True)

        assert target.list_versions("temp/versioned:item") == ["1.0.0", "1.0.1"]
        assert target.load("temp/versioned:item", version="1.0.0") == 1
        assert target.load("temp/versioned:item", version="1.0.1") == 2


def test_update_store_latest_only_copies_latest_value_to_default_mount():
    with TemporaryDirectory() as src, TemporaryDirectory() as dst:
        source = Store(mounts={"a": Registry(backend=src, version_objects=True, mutable=True)}, default_mount="a")
        target = Store(mounts={"temp": Registry(backend=dst, version_objects=True, mutable=True)})

        source.save("a/latest:item", 1)
        source.save("a/latest:item", 2)

        target.update(source, sync_all_versions=False)

        assert target.load("temp/latest:item") == 2
        assert target.list_versions("temp/latest:item") == ["1.0.0"]


def test_store_str_marks_default_mount(two_mount_store):
    text = str(two_mount_store)
    assert "[*a]" in text
    assert "Default Mount: `a`" in text
