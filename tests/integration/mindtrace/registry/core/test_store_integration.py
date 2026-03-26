import pytest

from mindtrace.registry import Registry, Store
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
    StoreLocationNotFound,
)


@pytest.fixture
def store_with_mounts(temp_dir):
    alpha = Registry(backend=temp_dir / "alpha", version_objects=True, mutable=True)
    beta = Registry(backend=temp_dir / "beta", version_objects=True, mutable=True)
    return Store(mounts={"alpha": alpha, "beta": beta}, default_mount="alpha")


def test_store_integration_key_helpers_and_registry_resolution(store_with_mounts):
    store = store_with_mounts

    assert store.has_mount("temp")
    assert store.has_mount("alpha")
    assert not store.has_mount("missing")

    assert store.parse_key("alpha/ns:item@1.0.0") == ("alpha", "ns:item", "1.0.0")
    assert store.parse_key("ns:item@1.0.0") == (None, "ns:item", "1.0.0")
    assert store.build_key("alpha", "ns:item", "1.0.0") == "alpha/ns:item@1.0.0"
    assert store.build_key("alpha", "ns:item") == "alpha/ns:item"

    assert store.resolve_registry("alpha") is store.get_mount("alpha").registry
    assert store.resolve_registry("alpha/ns:item") is store.get_mount("alpha").registry
    assert store.get_registry("alpha") is store.get_mount("alpha").registry

    with pytest.raises(StoreLocationNotFound):
        store.resolve_registry("ns:item")
    with pytest.raises(StoreLocationNotFound):
        store.build_key("missing", "ns:item")
    with pytest.raises(StoreKeyFormatError):
        store.parse_key("")
    with pytest.raises(StoreKeyFormatError):
        store.build_key("alpha", "")


def test_store_integration_save_load_batch_delete_and_len(store_with_mounts):
    store = store_with_mounts

    single_version = store.save("unqualified:item", {"a": 1})
    assert single_version == "1.0.0"
    assert store.load("alpha/unqualified:item") == {"a": 1}

    batch = store.save(
        ["alpha/batch:one", "beta/batch:two"],
        [{"x": 1}, {"y": 2}],
    )
    assert batch.success_count == 2
    assert batch.failure_count == 0

    loaded = store.load(["alpha/batch:one", "batch:two"])
    assert loaded.results == [{"x": 1}, {"y": 2}]

    assert len(store) >= 3
    assert "alpha/batch:one" in store.keys()
    assert "beta/batch:two" in store.keys()
    assert {k for k, _ in store.items("alpha")} >= {"alpha/unqualified:item", "alpha/batch:one"}
    assert {str(v) for v in store.values("beta")} >= {"{'y': 2}"}

    delete_result = store.delete(["alpha/batch:one", "beta/batch:two"])
    assert delete_result.success_count == 2
    assert not store.has_object("alpha/batch:one")
    assert not store.has_object("beta/batch:two")

    with pytest.raises(ValueError):
        store.save(["alpha/a", "beta/b"], [1])
    with pytest.raises(ValueError):
        store.load(["alpha/a", "beta/b"], version=["latest"])
    with pytest.raises(ValueError):
        store.delete(["alpha/a", "beta/b"], version=[None])


def test_store_integration_ambiguity_cache_and_contains(store_with_mounts):
    store = store_with_mounts
    store.save("alpha/shared:item", 1)
    store.save("beta/shared:item", 2)

    assert store.has_object("shared:item")
    assert "alpha/shared:item" in store
    assert ["alpha/shared:item", "beta/shared:item"] in store

    with pytest.raises(StoreAmbiguousObjectError):
        store.load("shared:item")
    with pytest.raises(StoreAmbiguousObjectError):
        store.get("shared:item")
    with pytest.raises(StoreAmbiguousObjectError):
        store.pop("shared:item")

    store.save("beta/cache:item", "v")
    assert store.cache_lookup_locations("cache:item") == ["beta"]
    assert store.load("cache:item") == "v"
    store.clear_location_cache()
    assert store.cache_lookup_locations("cache:item") == []


def test_store_integration_info_copy_move_pop_setdefault_get_and_dunders(store_with_mounts):
    store = store_with_mounts
    store["alpha/source:item"] = {"payload": True}
    assert store["alpha/source:item"] == {"payload": True}

    top_info = store.info()
    assert top_info["default_mount"] == "alpha"
    assert {"temp", "alpha", "beta"}.issubset(top_info["mounts"].keys())

    item_info = store.info("source:item")
    assert item_info

    copied_version = store.copy("alpha/source:item", target="beta/copied:item")
    assert copied_version == "1.0.0"
    assert store.load("beta/copied:item") == {"payload": True}

    moved_version = store.move("beta/copied:item", target="alpha/moved:item")
    assert moved_version == "1.0.0"
    assert store.load("alpha/moved:item") == {"payload": True}
    with pytest.raises(RegistryObjectNotFound):
        store.load("beta/copied:item")

    assert store.setdefault("created:item", [1, 2, 3]) == [1, 2, 3]
    assert store.load("alpha/created:item") == [1, 2, 3]
    assert store.get("missing:item", "fallback") == "fallback"

    assert store.pop("moved:item") == {"payload": True}
    assert store.pop("missing:item", "fallback") == "fallback"
    with pytest.raises(RegistryObjectNotFound):
        store.pop("missing:item")
    with pytest.raises(RegistryObjectNotFound):
        store.load("alpha/moved:item")

    del store["alpha/source:item"]
    with pytest.raises(RegistryObjectNotFound):
        store.load("alpha/source:item")


def test_store_integration_read_only_mount_and_batch_failures(temp_dir):
    writable = Registry(backend=temp_dir / "writable", version_objects=True, mutable=True)
    readonly = Registry(backend=temp_dir / "readonly", version_objects=True, mutable=True)
    store = Store(mounts={"w": writable, "ro": readonly}, default_mount="w")
    store.remove_mount("ro")
    store.add_mount("ro", readonly, read_only=True)

    with pytest.raises(PermissionError):
        store.save("ro/blocked:item", 1)
    with pytest.raises(PermissionError):
        store.delete("ro/blocked:item")

    store.save("w/good:item", 1)
    result = store.save(["w/ok:item", "ro/nope:item"], [1, 2])
    assert result.success_count == 1
    assert result.failure_count == 1
    assert any(key[0] == "ro/nope:item" for key in result.failed)

    load_result = store.load(["w/good:item", "missing:item"])
    assert load_result.success_count == 1
    assert load_result.failure_count == 1

    delete_result = store.delete(["w/good:item", "ro/nope:item"])
    assert delete_result.success_count == 1
    assert delete_result.failure_count == 1


def test_store_integration_update_and_mount_management(temp_dir):
    src_a = Registry(backend=temp_dir / "src_a", version_objects=True, mutable=True)
    src_b = Registry(backend=temp_dir / "src_b", version_objects=True, mutable=True)
    dst = Registry(backend=temp_dir / "dst", version_objects=True, mutable=True)

    source = Store(mounts={"a": src_a, "b": src_b}, default_mount="a")
    target = Store(mounts={"dest": dst}, default_mount="dest")

    source.save("a/versioned:item", "v1")
    source.save("a/versioned:item", "v2")
    source.save("b/other:item", {"k": "v"})

    target.update(source, sync_all_versions=True)
    assert target.list_versions("dest/versioned:item") == ["1.0.0", "1.0.1"]
    assert target.load("dest/other:item") == {"k": "v"}

    target2 = Store(
        mounts={"dest": Registry(backend=temp_dir / "dst2", version_objects=True, mutable=True)}, default_mount="dest"
    )
    target2.update(source, sync_all_versions=False)
    assert target2.list_versions("dest/versioned:item") == ["1.0.0"]
    assert target2.load("dest/versioned:item") == "v2"

    target2.update({"mapping:item": 5})
    assert target2.load("dest/mapping:item") == 5

    with pytest.raises(TypeError):
        target2.update([("bad", 1)])

    target2.save("dest/cache:item", "x")
    assert target2.load("cache:item") == "x"
    assert target2.cache_lookup_locations("cache:item") == ["dest"]
    target2.remove_mount("dest")
    assert target2.default_mount == "temp"
    assert target2.cache_lookup_locations("cache:item") == []

    with pytest.raises(ValueError):
        target2.remove_mount("temp")
