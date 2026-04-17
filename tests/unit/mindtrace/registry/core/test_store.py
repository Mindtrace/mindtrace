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
from mindtrace.registry.core.mount import LocalMountConfig, Mount


@pytest.fixture
def basic_store():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        store = Store.from_mounts(
            [
                Mount(name="a", backend="local", config=LocalMountConfig(uri=d1), is_default=True),
                Mount(name="b", backend="local", config=LocalMountConfig(uri=d2)),
            ]
        )
        yield store


@pytest.fixture
def versioned_store():
    with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
        store = Store(
            mounts={
                "a": Registry(backend=Path(d1), version_objects=True, mutable=True),
                "b": Registry(backend=Path(d2), version_objects=True, mutable=True),
            },
            default_mount="a",
        )
        yield store


def test_parse_key_with_and_without_mount(basic_store):
    assert basic_store.parse_key("a/foo@1") == ("a", "foo", "1")
    assert basic_store.parse_key("foo@2") == (None, "foo", "2")
    assert basic_store.parse_key("nested/path") == (None, "nested/path", None)


def test_set_default_mount_rejects_unknown_mount(basic_store):
    with pytest.raises(StoreLocationNotFound):
        basic_store.set_default_mount("missing")


def test_remove_mount_rejects_temp_mount(basic_store):
    with pytest.raises(ValueError):
        basic_store.remove_mount("temp")


def test_remove_mount_falls_back_default_to_temp(basic_store):
    basic_store.remove_mount("a")
    assert basic_store.default_mount == "temp"


def test_unqualified_load_raises_ambiguity_when_present_in_multiple_mounts(basic_store):
    basic_store.save("a/shared", {"from": "a"})
    basic_store.save("b/shared", {"from": "b"})
    with pytest.raises(StoreAmbiguousObjectError):
        basic_store.load("shared")


def test_unqualified_load_raises_not_found(basic_store):
    with pytest.raises(RegistryObjectNotFound):
        basic_store.load("missing")


def test_has_object_checks_across_mounts(basic_store):
    basic_store.save("b/item", {"ok": True})
    assert basic_store.has_object("item") is True
    assert basic_store.has_object("missing") is False


def test_batch_save_load_delete_round_trip(basic_store):
    save_result = basic_store.save(["x", "y"], [{"n": 1}, {"n": 2}])
    assert save_result.success_count == 2

    load_result = basic_store.load(["x", "y"])
    assert load_result.success_count == 2
    assert load_result.results[0]["n"] == 1
    assert load_result.results[1]["n"] == 2

    delete_result = basic_store.delete(["x", "y"])
    assert delete_result.success_count == 2


def test_list_versions_requires_qualified_name(basic_store):
    with pytest.raises(ValueError):
        basic_store.list_versions("unqualified")


def test_info_without_name_returns_store_info(basic_store):
    info = basic_store.info()
    assert info["default_mount"] == basic_store.default_mount
    assert "mounts" in info


def test_info_with_unqualified_name_resolves_location(basic_store):
    basic_store.save("only-here", {"hello": "world"})
    info = basic_store.info("only-here")
    assert info is not None


def test_copy_and_move_between_mounts(basic_store):
    basic_store.save("a/original", {"v": 1})
    copy_result = basic_store.copy("a/original", target="b/copied")
    assert copy_result is not None
    assert basic_store.load("b/copied")["v"] == 1

    move_result = basic_store.move("b/copied", target="a/moved")
    assert move_result is not None
    assert basic_store.load("a/moved")["v"] == 1
    with pytest.raises(RegistryObjectNotFound):
        basic_store.load("b/copied")


def test_move_unqualified_source_deletes_from_resolved_mount(basic_store):
    basic_store.save("b/original", {"v": "from-b"})

    moved_version = basic_store.move("original", target="a/moved")

    assert moved_version is not None
    assert basic_store.load("a/moved")["v"] == "from-b"
    with pytest.raises(RegistryObjectNotFound):
        basic_store.load("b/original")


def test_move_unqualified_source_with_explicit_version_deletes_from_resolved_mount(versioned_store):
    versioned_store.save("b/versioned", {"v": "v1"}, version="1.0.0")
    versioned_store.save("b/versioned", {"v": "v2"}, version="1.0.1")

    moved_version = versioned_store.move("versioned", target="a/moved-versioned", source_version="1.0.0")

    assert moved_version is not None
    assert versioned_store.load("a/moved-versioned")["v"] == "v1"
    with pytest.raises(RegistryObjectNotFound):
        versioned_store.load("b/versioned", version="1.0.0")
    assert versioned_store.load("b/versioned", version="1.0.1")["v"] == "v2"


def test_move_unqualified_source_with_key_version_deletes_loaded_version(versioned_store):
    versioned_store.save("b/key-versioned", {"v": "v1"}, version="1.0.0")
    versioned_store.save("b/key-versioned", {"v": "v2"}, version="1.0.1")

    moved_version = versioned_store.move("key-versioned@1.0.0", target="a/moved-key-version")

    assert moved_version is not None
    assert versioned_store.load("a/moved-key-version")["v"] == "v1"
    with pytest.raises(RegistryObjectNotFound):
        versioned_store.load("b/key-versioned", version="1.0.0")
    assert versioned_store.load("b/key-versioned", version="1.0.1")["v"] == "v2"


def test_dict_like_helpers(basic_store):
    basic_store["alpha"] = {"v": 1}
    assert basic_store["alpha"]["v"] == 1
    assert "alpha" in basic_store
    assert basic_store.get("alpha")["v"] == 1
    popped = basic_store.pop("alpha")
    assert popped["v"] == 1
    assert "alpha" not in basic_store


def test_setdefault_and_update_helpers(basic_store):
    created = basic_store.setdefault("beta", {"v": 2})
    assert created["v"] == 2
    existing = basic_store.setdefault("beta", {"v": 99})
    assert existing["v"] == 2

    basic_store.update({"gamma": {"v": 3}, "delta": {"v": 4}})
    assert basic_store.load("gamma")["v"] == 3
    assert basic_store.load("delta")["v"] == 4


def test_update_from_other_store(basic_store):
    with TemporaryDirectory() as d:
        other = Store.from_mounts([Mount(name="src", backend="local", config=LocalMountConfig(uri=d), is_default=True)])
        other.save("src/item", {"v": 7})
        basic_store.update(other)
        assert basic_store.load("item")["v"] == 7


def test_location_cache_helpers(basic_store):
    basic_store.cache_update_location("foo", "a")
    assert basic_store.cache_lookup_locations("foo") == ["a"]
    basic_store.cache_update_location("foo", "b")
    assert basic_store.cache_lookup_locations("foo") == ["b", "a"]
    basic_store.cache_update_location("foo", "a")
    assert basic_store.cache_lookup_locations("foo") == ["a", "b"]
    basic_store.cache_evict_name("foo")
    assert basic_store.cache_lookup_locations("foo") == []
    basic_store.cache_update_location("foo", "a")
    basic_store.clear_location_cache()
    assert basic_store.cache_lookup_locations("foo") == []


def test_has_mount_false_path_and_list_mount_info(basic_store):
    assert basic_store.has_mount("missing") is False
    info = basic_store.list_mount_info()
    assert "a" in info
    assert "b" in info
    assert "temp" in info


def test_add_mount_rejects_invalid_input_type(basic_store):
    with pytest.raises(TypeError):
        basic_store.add_mount(object())


def test_parse_key_recognizes_existing_mount_prefix(basic_store):
    assert basic_store.parse_key("a/nested/path") == ("a", "nested/path", None)


def test_remove_mount_prunes_cache_references(basic_store):
    basic_store.cache_update_location("foo", "a")
    basic_store.cache_update_location("foo", "b")
    basic_store.remove_mount("b")
    assert basic_store.cache_lookup_locations("foo") == ["a"]


def test_qualified_has_object_and_delete(basic_store):
    basic_store.save("a/qitem", {"v": 1})
    assert basic_store.has_object("a/qitem") is True
    assert basic_store.delete("a/qitem") is None
    assert basic_store.has_object("a/qitem") is False


def test_get_and_pop_missing_defaults(basic_store):
    sentinel = {"missing": True}
    assert basic_store.get("missing", sentinel) is sentinel
    assert basic_store.pop("missing", sentinel) is sentinel
    with pytest.raises(RegistryObjectNotFound):
        basic_store.pop("missing")


def test_keys_values_items_and_len(basic_store):
    basic_store.save("one", {"v": 1})
    basic_store.save("two", {"v": 2})
    keys = list(basic_store.keys())
    values = list(basic_store.values())
    items = list(basic_store.items())
    assert len(basic_store) >= 2
    assert "a/one" in keys
    assert "a/two" in keys
    assert any(v["v"] == 1 for v in values)
    assert any(k == "a/one" and v["v"] == 1 for k, v in items)


def test_unqualified_delete_uses_default_mount(basic_store):
    basic_store.save("default-only", {"v": 1})
    basic_store.delete("default-only")
    with pytest.raises(RegistryObjectNotFound):
        basic_store.load("a/default-only")


def test_batch_delete_missing_is_noop_success(basic_store):
    result = basic_store.delete(["present", "missing"])
    assert result.success_count == 2
    assert result.failure_count == 0


def test_store_init_accepts_explicit_temp_and_named_mounts():
    with TemporaryDirectory() as temp_dir, TemporaryDirectory() as other_dir:
        temp_registry = Registry.from_mount(Mount(backend="local", config=LocalMountConfig(uri=temp_dir)))
        other_registry = Registry.from_mount(Mount(backend="local", config=LocalMountConfig(uri=other_dir)))

        store = Store(mounts={"temp": temp_registry, "other": other_registry}, default_mount="temp")

        assert store.get_mount("temp").registry is temp_registry
        assert store.get_mount("other").registry is other_registry


def test_mount_name_sanitization_and_auto_derivation(basic_store):
    with TemporaryDirectory() as d:
        unnamed_mount = Mount(backend="local", config=LocalMountConfig(uri=d))

        basic_store.add_mount(unnamed_mount)
        basic_store.add_mount(unnamed_mount)

        derived_mounts = [mount for mount in basic_store.list_mounts() if mount not in {"temp", "a", "b"}]
        assert len(derived_mounts) == 2
        assert any(mount.endswith("-2") for mount in derived_mounts)
        assert Store._sanitize_mount_name("!!!") == "mount"


def test_derive_mount_name_handles_registry_sources_and_multiple_collisions():
    with TemporaryDirectory() as d:
        registry = Registry.from_mount(Mount(backend="local", config=LocalMountConfig(uri=d)))
        store = Store(default_mount="temp")

        first_name = store._derive_mount_name(registry)
        store.add_mount(registry, name=first_name)
        store.add_mount(registry, name=f"{first_name}-2")

        assert store._derive_mount_name(registry) == f"{first_name}-3"


def test_add_mount_validates_generated_invalid_and_duplicate_names(basic_store):
    with TemporaryDirectory() as auto_dir, TemporaryDirectory() as dup_dir:
        basic_store.add_mount(Mount(backend="local", config=LocalMountConfig(uri=auto_dir)))
        assert len([mount for mount in basic_store.list_mounts() if mount not in {"temp", "a", "b"}]) == 1

        with pytest.raises(ValueError, match="Invalid mount name"):
            basic_store.add_mount(
                Mount(backend="local", config=LocalMountConfig(uri=dup_dir)),
                name="bad/name",
            )

        basic_store.add_mount(Mount(name="dup", backend="local", config=LocalMountConfig(uri=dup_dir)))
        with pytest.raises(ValueError, match="already exists"):
            basic_store.add_mount(
                Mount(name="dup", backend="local", config=LocalMountConfig(uri=dup_dir)),
            )


def test_remove_and_get_mount_raise_for_unknown_mount(basic_store):
    with pytest.raises(StoreLocationNotFound):
        basic_store.remove_mount("missing")

    with pytest.raises(StoreLocationNotFound):
        basic_store.get_mount("missing")


def test_remove_mount_evicts_last_cached_location(basic_store):
    basic_store.cache_update_location("foo", "b")
    basic_store.remove_mount("b")

    assert basic_store.cache_lookup_locations("foo") == []


def test_parse_and_build_key_validation_errors(basic_store):
    with pytest.raises(StoreKeyFormatError, match="empty"):
        basic_store.parse_key("   ")

    with pytest.raises(StoreKeyFormatError, match="Invalid key"):
        basic_store.parse_key("@1")

    with pytest.raises(StoreKeyFormatError, match="Invalid key"):
        basic_store.parse_key("a/")

    with pytest.raises(StoreLocationNotFound):
        basic_store.build_key("missing", "name")

    with pytest.raises(StoreKeyFormatError, match="name cannot be empty"):
        basic_store.build_key("a", "")


def test_resolve_registry_and_get_registry_helpers(basic_store):
    assert basic_store.resolve_registry("a") is basic_store.get_mount("a").registry
    assert basic_store.get_registry("a/item") is basic_store.get_mount("a").registry

    with pytest.raises(StoreLocationNotFound, match="No mount specified"):
        basic_store.resolve_registry("item")


def test_cache_helpers_noop_when_location_cache_disabled():
    store = Store(enable_location_cache=False)

    store.cache_update_location("foo", "temp")

    assert store.cache_lookup_locations("foo") == []


def test_read_only_mount_blocks_save_and_delete(basic_store):
    with TemporaryDirectory() as d:
        basic_store.add_mount(Mount(name="ro", backend="local", config=LocalMountConfig(uri=d), read_only=True))

        with pytest.raises(PermissionError, match="read-only"):
            basic_store.save("ro/item", {"v": 1})

        basic_store.get_mount("ro").registry.save("item", {"v": 1})
        with pytest.raises(PermissionError, match="read-only"):
            basic_store.delete("ro/item")


def test_batch_operations_validate_lengths(basic_store):
    with pytest.raises(ValueError, match="lengths must match"):
        basic_store.save(["one", "two"], [{"v": 1}], version=[None, None])

    with pytest.raises(ValueError, match="same length"):
        basic_store.load(["one", "two"], version=["1"])

    with pytest.raises(ValueError, match="same length"):
        basic_store.delete(["one", "two"], version=["1"])


def test_batch_save_records_per_item_errors(basic_store, monkeypatch):
    original_single_save = basic_store._single_save

    def fake_single_save(key, obj, **kwargs):
        if key == "bad":
            raise RuntimeError("boom")
        return original_single_save(key, obj, **kwargs)

    monkeypatch.setattr(basic_store, "_single_save", fake_single_save)

    result = basic_store.save(["good", "bad"], [{"v": 1}, {"v": 2}])

    assert result.success_count == 1
    assert result.failure_count == 1
    assert ("a/good", "1.0.0") in result.succeeded
    assert ("a/bad", "latest") in result.failed
    assert result.errors[("a/bad", "latest")]["error"] == "RuntimeError"


def test_batch_load_records_per_item_errors(basic_store, monkeypatch):
    def fake_single_load(key, version="latest", output_dir=None, verify=None, **kwargs):
        if key == "bad":
            raise RuntimeError("boom")
        return {"key": key, "version": version}

    monkeypatch.setattr(basic_store, "_single_load", fake_single_load)

    result = basic_store.load(["good", "bad"], version=["1", "2"])

    assert result.success_count == 1
    assert result.failure_count == 1
    assert ("good", "1") in result.succeeded
    assert ("bad", "2") in result.failed
    assert result.errors[("bad", "2")]["message"] == "boom"


def test_batch_delete_records_per_item_errors(basic_store, monkeypatch):
    def fake_single_delete(key, version=None):
        if key == "bad":
            raise RuntimeError("boom")

    monkeypatch.setattr(basic_store, "_single_delete", fake_single_delete)

    result = basic_store.delete(["good", "bad"], version=["1", "2"])

    assert result.success_count == 1
    assert result.failure_count == 1
    assert ("good", "1") in result.succeeded
    assert ("bad", "2") in result.failed
    assert result.errors[("bad", "2")]["error"] == "RuntimeError"


def test_listing_helpers_with_mount_specific_queries(basic_store):
    basic_store.save("a/item", {"v": 1}, version="1")
    basic_store.save("b/other", {"v": 3})

    assert basic_store.list_objects("a") == ["a/item"]
    assert basic_store.list_versions("a/item") == ["1.0.0"]
    assert basic_store.list_objects_and_versions("a") == {"a/item": ["1.0.0"]}

    all_objects = basic_store.list_objects_and_versions()
    assert all_objects["a/item"] == ["1.0.0"]
    assert all_objects["b/other"] == ["1.0.0"]


def test_dict_dunder_helpers_for_delete_contains_and_str(basic_store):
    basic_store["alpha"] = {"v": 1}
    basic_store["beta"] = {"v": 2}

    assert ["alpha", "beta"] in basic_store
    del basic_store["beta"]
    assert "beta" not in basic_store

    rendered = basic_store.__str__(color=False)
    assert "Store" in rendered
    assert "[*a]" in rendered
    assert "Default Mount: `a`" in rendered


def test_update_from_store_without_syncing_all_versions():
    with TemporaryDirectory() as src_dir, TemporaryDirectory() as dst_dir:
        other = Store.from_mounts(
            [Mount(name="src", backend="local", config=LocalMountConfig(uri=src_dir), is_default=True)]
        )
        target = Store.from_mounts(
            [
                Mount(
                    name="dst",
                    backend="local",
                    config=LocalMountConfig(uri=dst_dir),
                    is_default=True,
                    registry_options={"mutable": True},
                )
            ]
        )
        other.save("src/item", {"v": 2})
        other.save("src/second", {"v": 3})
        target.save("item", {"v": 0})

        target.update(other, sync_all_versions=False)

        assert target.load("item")["v"] == 2
        assert target.load("second")["v"] == 3
        assert target.list_versions("dst/item") == ["1.0.0"]


def test_update_rejects_non_mapping_input(basic_store):
    with pytest.raises(TypeError, match="mapping must be a mapping or Store"):
        basic_store.update(object())


def test_store_direct_upload_round_trip_on_mount(basic_store):
    target = basic_store.create_direct_upload_target("a/store-bytes", upload_id="store-up-1")
    assert target["mount"] == "a"
    staged = target["staged_target"]

    Path(staged["path"]).write_bytes(b"store-payload")
    assert basic_store.inspect_direct_upload_target("a/store-bytes", staged_target=staged)["exists"] is True
    ver = basic_store.commit_direct_upload(
        "a/store-bytes",
        staged_target=staged,
        version="1.0.0",
        metadata=None,
    )
    assert ver == "1.0.0"


def test_store_commit_direct_upload_uses_key_version_when_omitted():
    """Store passes key-embedded version into Registry when ``version`` is omitted."""
    with TemporaryDirectory() as d1:
        store = Store.from_mounts(
            [
                Mount(
                    name="a",
                    backend="local",
                    config=LocalMountConfig(uri=d1),
                    is_default=True,
                    registry_options={"version_objects": True, "mutable": True},
                ),
            ]
        )
        target = store.create_direct_upload_target("a/keyver@2.0.0", upload_id="kv1")
        staged = target["staged_target"]
        Path(staged["path"]).write_bytes(b"v")
        ver = store.commit_direct_upload(
            "a/keyver@2.0.0",
            staged_target=staged,
            version=None,
            metadata=None,
        )
        assert ver == "2.0.0"


def test_store_direct_upload_unqualified_key_uses_default_mount():
    with TemporaryDirectory() as d1:
        store = Store.from_mounts(
            [
                Mount(
                    name="a",
                    backend="local",
                    config=LocalMountConfig(uri=d1),
                    is_default=True,
                    registry_options={"version_objects": True, "mutable": True},
                ),
            ]
        )
        target = store.create_direct_upload_target("solo-obj", upload_id="uq1")
        assert target["mount"] == "a"
        staged = target["staged_target"]
        Path(staged["path"]).write_bytes(b"1")
        assert store.inspect_direct_upload_target("solo-obj", staged_target=staged)["exists"] is True
        assert store.cleanup_direct_upload_target("solo-obj", staged_target=staged) is True
