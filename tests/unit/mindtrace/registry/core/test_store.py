"""Behavioral unit tests for core.store."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from mindtrace.registry import LocalRegistryBackend, Registry, S3RegistryBackend, Store
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    StoreAmbiguousObjectError,
    StoreKeyFormatError,
    StoreLocationNotFound,
)
from mindtrace.registry.core.mount import LocalMountConfig, Mount
from tests.registry_test_helpers import RevisionedIntMaterializer
from tests.unit.mindtrace.registry.backends.test_s3_registry_backend import MockS3Handler
from tests.unit.mindtrace.registry.core.test_registry import _replicas, _stored_files


@pytest.fixture(params=["local", "cached"])
def move_store(request, tmp_path):
    source = (
        request.getfixturevalue("cached_mock_registry")
        if request.param == "cached"
        else Registry(backend=tmp_path / "source", version_objects=True, mutable=True)
    )
    destination = Registry(backend=tmp_path / "destination", version_objects=True, mutable=True)
    return Store(mounts={"src": source, "dst": destination}, default_mount="dst")


def _assert_exact_version_removed(backend, before, name, version):
    """Compare committed artifacts; deletion may also clean staging for its target."""
    if isinstance(backend, LocalRegistryBackend):
        metadata = f"_meta_{name}@{version}.yaml"
        payload = f"{name}/{version}/"
        staging = "_staging/"
    else:
        root = f"{backend._prefix}/" if backend._prefix else ""
        metadata = f"{root}_meta_{name}@{version}.json"
        payload = f"{root}objects/{name}/{version}/"
        staging = f"{root}_staging/"
    assert metadata in before
    assert any(key.startswith(payload) for key in before)
    expected = {
        key: value for key, value in before.items() if key != metadata and not key.startswith((payload, staging))
    }
    actual = {key: value for key, value in _stored_files(backend).items() if not key.startswith(staging)}
    assert actual == expected


@pytest.fixture
def store(tmp_path):
    return Store(
        mounts={
            "a": Registry(backend=tmp_path / "a", version_objects=True, mutable=True),
            "b": Registry(backend=tmp_path / "b", version_objects=True, mutable=True),
        },
        default_mount="a",
    )


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


@pytest.fixture
def download_store(tmp_path, cached_mock_registry):
    local = Registry(backend=tmp_path / "local", version_objects=True)
    store = Store(mounts={"local": local}, default_mount="local")
    store.add_mount(cached_mock_registry, name="remote", read_only=True)
    return store


class TestMountRouting:
    def test_parse_key_with_and_without_mount(self, basic_store):
        assert basic_store.parse_key("a/foo@1") == ("a", "foo", "1")
        assert basic_store.parse_key("foo@2") == (None, "foo", "2")
        assert basic_store.parse_key("nested/path") == (None, "nested/path", None)

    def test_set_default_mount_rejects_unknown_mount(self, basic_store):
        with pytest.raises(StoreLocationNotFound):
            basic_store.set_default_mount("missing")

    def test_remove_mount_rejects_temp_mount(self, basic_store):
        with pytest.raises(ValueError):
            basic_store.remove_mount("temp")

    def test_remove_mount_falls_back_default_to_temp(self, basic_store):
        basic_store.remove_mount("a")
        assert basic_store.default_mount == "temp"

    def test_unqualified_load_raises_ambiguity_when_present_in_multiple_mounts(self, basic_store):
        basic_store.save("a/shared", {"from": "a"})
        basic_store.save("b/shared", {"from": "b"})
        with pytest.raises(StoreAmbiguousObjectError):
            basic_store.load("shared")

    def test_has_object_checks_across_mounts(self, basic_store):
        basic_store.save("b/item", {"ok": True})
        assert basic_store.has_object("item") is True
        assert basic_store.has_object("missing") is False

    def test_has_mount_false_path_and_list_mount_info(self, basic_store):
        assert basic_store.has_mount("missing") is False
        info = basic_store.list_mount_info()
        assert "a" in info
        assert "b" in info
        assert "temp" in info

    def test_add_mount_rejects_invalid_input_type(self, basic_store):
        with pytest.raises(TypeError):
            basic_store.add_mount(object())

    def test_parse_key_recognizes_existing_mount_prefix(self, basic_store):
        assert basic_store.parse_key("a/nested/path") == ("a", "nested/path", None)

    def test_unqualified_delete_uses_default_mount(self, basic_store):
        basic_store.save("a/shared", {"from": "a"})
        basic_store.save("b/shared", {"from": "b"})
        basic_store.delete("shared")
        assert not basic_store.has_object("a/shared")
        assert basic_store.load("b/shared") == {"from": "b"}

    def test_store_init_accepts_explicit_temp_and_named_mounts(self):
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as other_dir:
            temp_registry = Registry.from_mount(Mount(backend="local", config=LocalMountConfig(uri=temp_dir)))
            other_registry = Registry.from_mount(Mount(backend="local", config=LocalMountConfig(uri=other_dir)))

            store = Store(mounts={"temp": temp_registry, "other": other_registry}, default_mount="temp")

            assert store.get_mount("temp").registry is temp_registry
            assert store.get_mount("other").registry is other_registry

    def test_mount_name_sanitization_and_auto_derivation(self, basic_store):
        with TemporaryDirectory() as d:
            unnamed_mount = Mount(backend="local", config=LocalMountConfig(uri=d))

            basic_store.add_mount(unnamed_mount)
            basic_store.add_mount(unnamed_mount)

            derived_mounts = [mount for mount in basic_store.list_mounts() if mount not in {"temp", "a", "b"}]
            assert len(derived_mounts) == 2
            assert any(mount.endswith("-2") for mount in derived_mounts)
            assert Store._sanitize_mount_name("!!!") == "mount"

    def test_derive_mount_name_handles_registry_sources_and_multiple_collisions(self):
        with TemporaryDirectory() as d:
            registry = Registry.from_mount(Mount(backend="local", config=LocalMountConfig(uri=d)))
            store = Store(default_mount="temp")

            first_name = store._derive_mount_name(registry)
            store.add_mount(registry, name=first_name)
            store.add_mount(registry, name=f"{first_name}-2")

            assert store._derive_mount_name(registry) == f"{first_name}-3"

    def test_add_mount_validates_generated_invalid_and_duplicate_names(self, basic_store):
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

    def test_remove_and_get_mount_raise_for_unknown_mount(self, basic_store):
        with pytest.raises(StoreLocationNotFound):
            basic_store.remove_mount("missing")

        with pytest.raises(StoreLocationNotFound):
            basic_store.get_mount("missing")

    def test_parse_and_build_key_validation_errors(self, basic_store):
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

    def test_listing_helpers_with_mount_specific_queries(self, basic_store):
        basic_store.save("a/item", {"v": 1}, version="1")
        basic_store.save("b/other", {"v": 3})

        assert basic_store.list_objects("a") == ["a/item"]
        assert basic_store.list_versions("a/item") == ["1.0.0"]
        assert basic_store.list_objects_and_versions("a") == {"a/item": ["1.0.0"]}

        all_objects = basic_store.list_objects_and_versions()
        assert all_objects["a/item"] == ["1.0.0"]
        assert all_objects["b/other"] == ["1.0.0"]

    def test_qualified_slash_key_is_stable_when_a_matching_mount_is_added(self, basic_store, tmp_path):
        """S1 control: canonical qualified identity survives changes to other mounts."""
        key = basic_store.build_key("a", "nested/path", "1.0.0")
        basic_store.save(key, {"v": 1})
        assert basic_store.parse_key(key) == ("a", "nested/path", "1.0.0")
        basic_store.add_mount(Registry(backend=tmp_path / "extra"), name="nested")
        assert basic_store.parse_key(key) == ("a", "nested/path", "1.0.0")
        assert basic_store.load(key) == {"v": 1}

    def test_membership_does_not_choose_an_ambiguous_mount(self, basic_store):
        """S5 control: existence across mounts is distinct from unique resolution."""
        basic_store.save("a/shared", {"from": "a"})
        basic_store.save("b/shared", {"from": "b"})
        assert "shared" in basic_store
        with pytest.raises(StoreAmbiguousObjectError):
            _ = basic_store["shared"]
        assert basic_store["a/shared"] == {"from": "a"}
        assert basic_store["b/shared"] == {"from": "b"}


class TestReads:
    def test_unqualified_load_raises_not_found(self, basic_store):
        with pytest.raises(RegistryObjectNotFound):
            basic_store.load("missing")


class TestBatchOperations:
    def test_batch_save_load_delete_round_trip(self, basic_store):
        save_result = basic_store.save(["x", "y"], [{"n": 1}, {"n": 2}])
        assert save_result.success_count == 2

        load_result = basic_store.load(["x", "y"])
        assert load_result.success_count == 2
        assert load_result.results[0]["n"] == 1
        assert load_result.results[1]["n"] == 2

        delete_result = basic_store.delete(["x", "y"])
        assert delete_result.success_count == 2

    def test_batch_delete_reports_missing_item_separately(self, basic_store):
        basic_store.save("present", "value")
        result = basic_store.delete(["present", "missing"])
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.errors[("missing", "latest")]["error"] == "RegistryObjectNotFound"
        assert not basic_store.has_object("a/present")

    def test_batch_operations_validate_lengths(self, basic_store):
        with pytest.raises(ValueError, match="same length"):
            basic_store.save(["one", "two"], [{"v": 1}], version=[None, None])
        assert basic_store.get_mount(basic_store.default_mount).registry.list_objects() == []

        with pytest.raises(ValueError, match="same length"):
            basic_store.load(["one", "two"], version=["1"])

        with pytest.raises(ValueError, match="same length"):
            basic_store.delete(["one", "two"], version=["1"])

    def test_batch_save_records_per_item_errors(self, basic_store, monkeypatch):
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

    def test_batch_load_records_per_item_errors(self, basic_store, monkeypatch):
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

    def test_batch_delete_records_per_item_errors(self, basic_store, monkeypatch):
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


class TestVersioning:
    def test_list_versions_requires_qualified_name(self, basic_store):
        with pytest.raises(ValueError):
            basic_store.list_versions("unqualified")

    def test_update_from_store_without_syncing_all_versions(self):
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

    def test_pop_without_version_deletes_all_versions(self, versioned_store):
        """pop('name') must delete every version and return the latest value."""
        versioned_store.save("a/x", 1, version="1.0.0")
        versioned_store.save("a/x", 2, version="2.0.0")
        assert versioned_store.pop("a/x") == 2
        assert versioned_store.get_mount("a").registry.list_versions("x") == []


class TestDiscovery:
    def test_info_without_name_returns_store_info(self, basic_store):
        info = basic_store.info()
        assert info["default_mount"] == basic_store.default_mount
        assert "mounts" in info

    def test_info_with_unqualified_name_resolves_location(self, basic_store):
        basic_store.save("only-here", {"hello": "world"})
        info = basic_store.info("only-here")
        assert info is not None


class TestCopyAndMove:
    def test_copy_and_move_between_mounts(self, basic_store):
        basic_store.save("a/original", {"v": 1})
        copy_result = basic_store.copy("a/original", target="b/copied")
        assert copy_result is not None
        assert basic_store.load("b/copied")["v"] == 1

        move_result = basic_store.move("b/copied", target="a/moved")
        assert move_result is not None
        assert basic_store.load("a/moved")["v"] == 1
        with pytest.raises(RegistryObjectNotFound):
            basic_store.load("b/copied")

    def test_move_unqualified_source_deletes_from_resolved_mount(self, basic_store):
        basic_store.save("b/original", {"v": "from-b"})

        moved_version = basic_store.move("original", target="a/moved")

        assert moved_version is not None
        assert basic_store.load("a/moved")["v"] == "from-b"
        with pytest.raises(RegistryObjectNotFound):
            basic_store.load("b/original")

    def test_move_unqualified_source_with_explicit_version_deletes_from_resolved_mount(self, versioned_store):
        versioned_store.save("b/versioned", {"v": "v1"}, version="1.0.0")
        versioned_store.save("b/versioned", {"v": "v2"}, version="1.0.1")

        moved_version = versioned_store.move("versioned", target="a/moved-versioned", source_version="1.0.0")

        assert moved_version is not None
        assert versioned_store.load("a/moved-versioned")["v"] == "v1"
        with pytest.raises(RegistryObjectNotFound):
            versioned_store.load("b/versioned", version="1.0.0")
        assert versioned_store.load("b/versioned", version="1.0.1")["v"] == "v2"

    def test_move_unqualified_source_with_key_version_deletes_loaded_version(self, versioned_store):
        versioned_store.save("b/key-versioned", {"v": "v1"}, version="1.0.0")
        versioned_store.save("b/key-versioned", {"v": "v2"}, version="1.0.1")

        moved_version = versioned_store.move("key-versioned@1.0.0", target="a/moved-key-version")

        assert moved_version is not None
        assert versioned_store.load("a/moved-key-version")["v"] == "v1"
        with pytest.raises(RegistryObjectNotFound):
            versioned_store.load("b/key-versioned", version="1.0.0")
        assert versioned_store.load("b/key-versioned", version="1.0.1")["v"] == "v2"


class TestMappingOperations:
    def test_dict_like_helpers(self, basic_store):
        basic_store["alpha"] = {"v": 1}
        assert basic_store["alpha"]["v"] == 1
        assert "alpha" in basic_store
        assert basic_store.get("alpha")["v"] == 1
        popped = basic_store.pop("alpha")
        assert popped["v"] == 1
        assert "alpha" not in basic_store

    def test_setdefault_and_update_helpers(self, basic_store):
        created = basic_store.setdefault("beta", {"v": 2})
        assert created["v"] == 2
        existing = basic_store.setdefault("beta", {"v": 99})
        assert existing["v"] == 2

        basic_store.update({"gamma": {"v": 3}, "delta": {"v": 4}})
        assert basic_store.load("gamma")["v"] == 3
        assert basic_store.load("delta")["v"] == 4

    def test_update_from_other_store(self, basic_store):
        with TemporaryDirectory() as d:
            other = Store.from_mounts(
                [Mount(name="src", backend="local", config=LocalMountConfig(uri=d), is_default=True)]
            )
            other.save("src/item", {"v": 7})
            basic_store.update(other)
            assert basic_store.load("item")["v"] == 7

    def test_get_and_pop_missing_defaults(self, basic_store):
        sentinel = {"missing": True}
        assert basic_store.get("missing", sentinel) is sentinel
        assert basic_store.pop("missing", sentinel) is sentinel
        with pytest.raises(RegistryObjectNotFound):
            basic_store.pop("missing")

    def test_keys_values_items_and_len(self, basic_store):
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

    def test_update_rejects_non_mapping_input(self, basic_store):
        with pytest.raises(TypeError, match="mapping must be a mapping or Store"):
            basic_store.update(object())

    def test_update_from_store_preserves_noncolliding_objects(self, basic_store, tmp_path):
        """S7 control: test the established default-destination policy, not a new merge policy."""
        basic_store.save("a/first", {"from": "a"})
        basic_store.save("b/second", {"from": "b"})
        dest = Store(mounts={"target": Registry(backend=tmp_path / "target")}, default_mount="target")
        dest.update(basic_store)
        assert dest.load("target/first") == {"from": "a"}
        assert dest.load("target/second") == {"from": "b"}
        assert set(dest.keys("target")) == {"target/first", "target/second"}
        assert basic_store.load("a/first") == {"from": "a"}
        assert basic_store.load("b/second") == {"from": "b"}


class TestCaching:
    def test_location_cache_helpers(self, basic_store):
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

    def test_remove_mount_prunes_cache_references(self, basic_store):
        basic_store.cache_update_location("foo", "a")
        basic_store.cache_update_location("foo", "b")
        basic_store.remove_mount("b")
        assert basic_store.cache_lookup_locations("foo") == ["a"]

    def test_remove_mount_evicts_last_cached_location(self, basic_store):
        basic_store.cache_update_location("foo", "b")
        basic_store.remove_mount("b")

        assert basic_store.cache_lookup_locations("foo") == []

    def test_cache_helpers_noop_when_location_cache_disabled(self):
        store = Store(enable_location_cache=False)

        store.cache_update_location("foo", "temp")

        assert store.cache_lookup_locations("foo") == []


class TestDeletion:
    def test_qualified_has_object_and_delete(self, basic_store):
        basic_store.save("a/qitem", {"v": 1})
        assert basic_store.has_object("a/qitem") is True
        assert basic_store.delete("a/qitem") is None
        assert basic_store.has_object("a/qitem") is False

    def test_dict_dunder_helpers_for_delete_contains_and_str(self, basic_store):
        basic_store["alpha"] = {"v": 1}
        basic_store["beta"] = {"v": 2}

        assert ["alpha", "beta"] in basic_store
        del basic_store["beta"]
        assert "beta" not in basic_store

        rendered = basic_store.__str__(color=False)
        assert "Store" in rendered
        assert "[*a]" in rendered
        assert "Default Mount: `a`" in rendered


class TestRegistryAccess:
    def test_resolve_registry_and_get_registry_helpers(self, basic_store):
        assert basic_store.resolve_registry("a") is basic_store.get_mount("a").registry
        assert basic_store.get_registry("a/item") is basic_store.get_mount("a").registry

        with pytest.raises(StoreLocationNotFound, match="No mount specified"):
            basic_store.resolve_registry("item")


class TestReadOnlyMounts:
    def test_read_only_mount_blocks_save_and_delete(self, basic_store):
        with TemporaryDirectory() as d:
            basic_store.add_mount(Mount(name="ro", backend="local", config=LocalMountConfig(uri=d), read_only=True))

            with pytest.raises(PermissionError, match="read-only"):
                basic_store.save("ro/item", {"v": 1})

            basic_store.get_mount("ro").registry.save("item", {"v": 1})
            with pytest.raises(PermissionError, match="read-only"):
                basic_store.delete("ro/item")

    @pytest.mark.parametrize("operation", ["create", "commit", "cleanup"])
    @pytest.mark.parametrize("qualified", [False, True], ids=["default", "qualified"])
    def test_read_only_direct_writes_stop_before_backend_call(self, store, monkeypatch, operation, qualified):
        owner = store.get_mount("b").registry
        staged = owner.create_direct_upload_target("existing-upload")["staged_target"]
        Path(staged["path"]).write_bytes(b"owned")
        store.remove_mount("b")
        store.add_mount(owner, name="b", read_only=True)
        if not qualified:
            store.set_default_mount("b")
        key = "b/item" if qualified else "item"
        method = {
            "create": "create_direct_upload_target",
            "commit": "commit_direct_upload",
            "cleanup": "cleanup_direct_upload_target",
        }[operation]
        mutation = Mock(wraps=getattr(owner.backend, method))
        monkeypatch.setattr(owner.backend, method, mutation)
        delegation = Mock(wraps=getattr(owner, method))
        monkeypatch.setattr(owner, method, delegation)
        cache_update = Mock(wraps=store.cache_update_location)
        monkeypatch.setattr(store, "cache_update_location", cache_update)
        with pytest.raises(PermissionError, match="Mount 'b' is read-only"):
            if operation == "create":
                store.create_direct_upload_target(key, upload_id="new-upload")
            elif operation == "commit":
                store.commit_direct_upload(key, staged_target=staged, version="1.0.0")
            else:
                store.cleanup_direct_upload_target(key, staged_target=staged)
        delegation.assert_not_called()
        mutation.assert_not_called()
        cache_update.assert_not_called()
        assert Path(staged["path"]).read_bytes() == b"owned"
        assert not owner.has_object("item", "1.0.0")

    @pytest.mark.parametrize("qualified", [False, True], ids=["default", "qualified"])
    def test_writable_direct_upload_ignores_other_read_only_mount(self, store, qualified):
        """Upload routing checks the selected mount, not every mount or always the default."""
        other = store.get_mount("a").registry
        store.remove_mount("a")
        store.add_mount(other, name="a", read_only=True)
        store.set_default_mount("a" if qualified else "b")
        key = "b/item" if qualified else "item"

        target = store.create_direct_upload_target(key, upload_id="writable-upload")
        assert target["mount"] == "b"
        assert target["name"] == "item"
        staged = target["staged_target"]
        Path(staged["path"]).write_bytes(b"payload")
        assert store.inspect_direct_upload_target(key, staged_target=staged)["exists"] is True

        assert store.commit_direct_upload(key, staged_target=staged, version="1.0.0") == "1.0.0"
        assert store.load(key, version="1.0.0") == b"payload"
        assert not Path(staged["path"]).exists()
        assert not other.has_object("item", "1.0.0")

        abandoned = store.create_direct_upload_target(key, upload_id="abandoned-upload")["staged_target"]
        Path(abandoned["path"]).write_bytes(b"unused")
        assert store.cleanup_direct_upload_target(key, staged_target=abandoned) is True
        assert not Path(abandoned["path"]).exists()
        assert store.load(key, version="1.0.0") == b"payload"

    @pytest.mark.parametrize("qualified", [False, True], ids=["default", "qualified"])
    def test_read_only_mount_allows_direct_upload_inspection_and_reads(self, store, qualified):
        """Read-only mounts retain read access to objects and existing upload targets."""
        owner = store.get_mount("b").registry
        owner.save("item", b"existing", version="1.0.0")
        staged = owner.create_direct_upload_target("existing-upload")["staged_target"]
        Path(staged["path"]).write_bytes(b"staged")
        store.remove_mount("b")
        store.add_mount(owner, name="b", read_only=True)
        if not qualified:
            store.set_default_mount("b")
        key = "b/item" if qualified else "item"

        assert store.load(key, version="1.0.0") == b"existing"
        inspection = store.inspect_direct_upload_target(key, staged_target=staged)
        assert inspection["exists"] is True
        assert inspection["size_bytes"] == len(b"staged")
        assert store.create_direct_download_url(key, version="1.0.0") is None
        assert Path(staged["path"]).read_bytes() == b"staged"

    @pytest.mark.parametrize("qualified", [False, True], ids=["default", "qualified"])
    def test_read_only_mount_allows_direct_download_urls(self, store, cached_mock_registry, qualified):
        """Read-only remote mounts can still issue single and batch download URLs."""
        remote = cached_mock_registry
        remote.save("item", b"existing", version="1.0.0")
        expected = remote.create_direct_download_url("item", version="1.0.0")
        assert expected.startswith("https://example.invalid/")
        store.add_mount(remote, name="remote", read_only=True)
        if not qualified:
            store.set_default_mount("remote")
        key = "remote/item" if qualified else "item"

        assert store.create_direct_download_url(key, version="1.0.0") == expected
        assert store.create_direct_download_urls("remote" if qualified else "", ["item"], ["1.0.0"]) == [expected]


class TestDirectTransfers:
    def test_store_direct_upload_round_trip_on_mount(self, basic_store):
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

    def test_store_commit_direct_upload_uses_key_version_when_omitted(self):
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

    def test_store_direct_upload_unqualified_key_uses_default_mount(self):
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


class TestMissingDeletion:
    def test_store_delegates_missing_delete_policy(self, tmp_path):
        registry = Registry(backend=tmp_path / "registry", version_objects=False)
        store = Store(mounts={"main": registry}, default_mount="main")
        with pytest.raises(RegistryObjectNotFound):
            store.delete("main/missing")
        with pytest.raises(RegistryObjectNotFound):
            del store["main/missing"]
        registry.save("present", 7)
        result = store.delete(["main/present", "main/missing"])
        assert result.success_count == result.failure_count == 1
        assert result.errors[("main/missing", "latest")]["error"] == "RegistryObjectNotFound"


class TestBatchSaveContracts:
    def test_store_shared_parameters_keep_existing_load_semantics(self, tmp_path):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        registry.register_materializer(int, RevisionedIntMaterializer)
        store = Store({"archive": registry}, default_mount="archive")
        result = store.save(["a", "b"], [1, 2], init_params={"offset": 10}, metadata={"source": "shared"})
        assert result.success_count == 2
        assert registry.load(["a", "b"]).results == [11, 12]
        for name in ("a", "b"):
            assert registry.info(name, "1")["metadata"] == {"source": "shared"}

    @pytest.mark.parametrize("alias", ["archive", "alias", "reopened"])
    @pytest.mark.parametrize("versions", [None, ["1", "1.0.0"]])
    def test_store_resolves_targets_before_saving_to_any_mount(self, tmp_path, monkeypatch, alias, versions):
        registry = Registry(backend=tmp_path / "registry", version_objects=True)
        other = Registry(backend=tmp_path / "other", version_objects=True)
        reopened = Registry(backend=tmp_path / "registry")
        store = Store(
            {"archive": registry, "alias": registry, "reopened": reopened, "other": other}, default_mount="archive"
        )
        save = Mock(wraps=other.save)
        monkeypatch.setattr(other, "save", save)
        with pytest.raises(ValueError, match="[Bb]atch|[Dd]uplicate|[Rr]epeated"):
            store.save(
                ["other/good", "item", f"{alias}/item"],
                [3, 1, 2],
                version=None if versions is None else ["1", *versions],
            )
        save.assert_not_called()
        assert registry.list_objects() == other.list_objects() == []

    def test_store_key_versions_and_distinct_targets_are_supported(self, tmp_path):
        first = Registry(backend=tmp_path / "first", version_objects=True)
        second = Registry(backend=tmp_path / "second", version_objects=True)
        store = Store({"first": first, "second": second}, default_mount="first")
        result = store.save(["item@1", "first/item@2", "second/item"], [1, 2, 3])
        assert result.results == ["1.0.0", "2.0.0", "1.0.0"]
        assert first.load("item", "1") == 1
        assert first.load("item", "2") == 2
        assert second.load("item") == 3
        # The explicit argument takes precedence over a version embedded in the key.
        with pytest.raises(ValueError):
            store.save(["item@3", "first/item@4"], [4, 5], version="5")
        assert first.list_versions("item") == ["1.0.0", "2.0.0"]

    @pytest.mark.parametrize("second_location", ["same", "prefix", "endpoint"])
    def test_store_remote_target_identity_uses_storage_location(self, tmp_path, monkeypatch, second_location):
        class ConfiguredS3Handler(MockS3Handler):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.endpoint = kwargs["endpoint"]
                self.secure = kwargs["secure"]
                self.presign_endpoint = self.endpoint
                self.presign_secure = self.secure

        monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", ConfiguredS3Handler)
        registries = []
        for index in range(2):
            backend = S3RegistryBackend(
                uri=tmp_path / str(index),
                endpoint="second.invalid" if index and second_location == "endpoint" else "first.invalid",
                prefix="second" if index and second_location == "prefix" else "first",
                access_key="test",
                secret_key="test",
                bucket="batch-tests",
                secure=False,
            )
            registries.append(Registry(backend=backend, version_objects=True, use_cache=False))
        store = Store({"first": registries[0], "second": registries[1]}, default_mount="first")
        if second_location == "same":
            with pytest.raises(ValueError, match="Duplicate"):
                store.save(["item", "second/item"], [1, 2], version="1")
            assert all(registry.list_objects() == [] for registry in registries)
        else:
            result = store.save(["item", "second/item"], [1, 2], version="1")
            assert result.results == ["1.0.0", "1.0.0"]
            assert [registry.load("item", "1") for registry in registries] == [1, 2]


class TestMove:
    @pytest.mark.parametrize(
        ("key", "kwargs"),
        [
            ("src/item", {}),
            ("item", {}),
            ("src/item@1", {}),
            ("item@1", {}),
            ("src/item", {"source_version": "1"}),
            ("item@2", {"source_version": "1"}),
        ],
    )
    def test_move_retains_source_identity_when_new_version_is_published(self, move_store, monkeypatch, key, kwargs):
        source = move_store.get_registry("src")
        destination = move_store.get_registry("dst")
        source.save("item", "copied", version="1")
        source.save("keep", "untouched", version="1")
        source.load("item", "1")  # Exercise eviction of an existing cached source replica.
        original_save = destination.save
        published = []
        snapshots = []

        def save_then_publish(*args, **save_kwargs):
            saved = original_save(*args, **save_kwargs)
            source.save("item", "newer", version="2")
            snapshots.extend((backend, _stored_files(backend)) for backend in _replicas(source))
            published.append("2.0.0")
            return saved

        monkeypatch.setattr(destination, "save", save_then_publish)
        assert move_store.move(key, target="dst/item", target_version="7", **kwargs) == "7.0.0"
        assert published == ["2.0.0"]
        assert destination.load("item", "7") == "copied"
        for backend, before in snapshots:
            _assert_exact_version_removed(backend, before, "item", "1.0.0")
        assert source.load("item", "2") == "newer"
        assert source.load("keep", "1") == "untouched"

    @pytest.mark.parametrize("qualified", [False, True])
    def test_move_read_only_source_rejects_before_load_or_write(self, move_store, monkeypatch, qualified):
        source = move_store.get_registry("src")
        source.save("item", "original", version="1")
        move_store.remove_mount("src")
        move_store.add_mount(source, name="src", read_only=True)
        source_files = _stored_files(source.backend)
        destination = move_store.get_registry("dst")
        destination_files = _stored_files(destination.backend)
        load = Mock(wraps=source.load)
        save = Mock(wraps=destination.save)
        monkeypatch.setattr(source, "load", load)
        monkeypatch.setattr(destination, "save", save)

        with pytest.raises(PermissionError, match="Mount 'src' is read-only"):
            move_store.move("src/item" if qualified else "item", target="dst/item")

        load.assert_not_called()
        save.assert_not_called()
        assert _stored_files(source.backend) == source_files
        assert _stored_files(destination.backend) == destination_files

    @pytest.mark.parametrize("versioned", [False, True])
    @pytest.mark.parametrize("digits", [2, 4])
    def test_move_unqualified_nested_source_to_same_default_name(self, tmp_path, monkeypatch, versioned, digits):
        source = Registry(backend=tmp_path / "src", version_objects=versioned, version_digits=digits)
        destination = Registry(backend=tmp_path / "dst", version_objects=versioned, version_digits=digits)
        store = Store(mounts={"src": source, "dst": destination}, default_mount="dst")
        version = source.save("nested/item", "original")
        source.save("nested/sibling", "keep")
        before = _stored_files(source.backend)
        resolve = Mock(wraps=store._resolve_load_location)
        monkeypatch.setattr(store, "_resolve_load_location", resolve)

        assert store.move("nested/item", target="nested/item") == version

        resolve.assert_called_once_with("nested/item", "latest")
        assert destination.load("nested/item") == "original"
        _assert_exact_version_removed(source.backend, before, "nested/item", version)
        assert source.load("nested/sibling") == "keep"

    @pytest.mark.parametrize(
        ("key", "kwargs", "expected"),
        [
            ("src/item", {}, "ten"),
            ("src/item", {"source_version": None}, "ten"),
            ("item@2", {}, "two"),
            ("src/item@2", {"source_version": "10"}, "ten"),
        ],
    )
    def test_move_preserves_version_selection_and_remaining_history(self, move_store, key, kwargs, expected):
        source = move_store.get_registry("src")
        source.save("item", "two", version="2")
        source.save("item", "ten", version="10")
        before = _stored_files(source.backend)
        version = "10.0.0" if expected == "ten" else "2.0.0"
        remaining = "2" if expected == "ten" else "10"

        assert move_store.move(key, target="dst/renamed@5", **kwargs) == "5.0.0"

        assert move_store.load("dst/renamed@5") == expected
        _assert_exact_version_removed(source.backend, before, "item", version)
        assert source.load("item", remaining) == ("two" if expected == "ten" else "ten")

    @pytest.mark.parametrize("stage", ["load", "save", "delete"])
    def test_move_propagates_errors_without_unintended_source_deletion(self, move_store, monkeypatch, stage):
        source = move_store.get_registry("src")
        destination = move_store.get_registry("dst")
        source.save("item", "original", version="1")
        before = _stored_files(source.backend)
        error = OSError(f"{stage} unavailable")
        operation = Mock(side_effect=error)
        monkeypatch.setattr(destination if stage == "save" else source, stage, operation)

        with pytest.raises(OSError) as caught:
            move_store.move("src/item", target="dst/item")

        assert caught.value is error
        operation.assert_called_once()
        assert _stored_files(source.backend) == before
        if stage == "delete":
            # No rollback guarantee: successful destination copy remains.
            assert destination.load("item") == "original"
        else:
            assert destination.list_versions("item") == []

    @pytest.mark.parametrize("key", ["src/missing", "missing", "src/item@99", "src/item@invalid"])
    def test_move_bad_source_never_writes_destination(self, move_store, monkeypatch, key):
        move_store.save("src/item", "keep", version="1")
        source_files = _stored_files(move_store.get_registry("src").backend)
        destination = move_store.get_registry("dst")
        save = Mock(wraps=destination.save)
        monkeypatch.setattr(destination, "save", save)
        error_type = ValueError if key.endswith("invalid") else RegistryObjectNotFound

        with pytest.raises(error_type):
            move_store.move(key, target="dst/item")

        save.assert_not_called()
        assert _stored_files(move_store.get_registry("src").backend) == source_files

    def test_move_ambiguous_source_never_writes(self, move_store, monkeypatch):
        move_store.save("src/item", "source", version="1")
        move_store.save("dst/item", "destination", version="1")
        destination = move_store.get_registry("dst")
        before = _stored_files(destination.backend)
        save = Mock(wraps=destination.save)
        monkeypatch.setattr(destination, "save", save)
        with pytest.raises(StoreAmbiguousObjectError):
            move_store.move("item", target="dst/other")
        save.assert_not_called()
        assert _stored_files(destination.backend) == before

    def test_move_read_only_destination_preserves_source(self, move_store):
        source = move_store.get_registry("src")
        source.save("item", "original", version="1")
        before = _stored_files(source.backend)
        destination = move_store.get_registry("dst")
        move_store.remove_mount("dst")
        move_store.add_mount(destination, name="dst", read_only=True)
        with pytest.raises(PermissionError, match="Mount 'dst' is read-only"):
            move_store.move("src/item", target="dst/item")
        assert _stored_files(source.backend) == before
        assert destination.list_versions("item") == []

    @pytest.mark.parametrize("qualified", [False, True])
    @pytest.mark.parametrize("version", ["latest", "1"])
    def test_move_backend_call_budget(self, move_store, monkeypatch, record_property, qualified, version):
        """Do not exceed the pre-fix I/O budget on the same cold initial state."""
        source = move_store.get_registry("src")
        source.save("item", "original", version="1")
        if source._cached:
            source.clear_cache()
        source._core._invalidate_versions_cache("item")
        calls = {}
        for mount_name in move_store.list_mounts():
            registry = move_store.get_registry(mount_name)
            for replica, backend in enumerate(_replicas(registry)):
                for method in ("list_versions", "has_object", "fetch_metadata", "pull", "push", "delete"):
                    spy = Mock(wraps=getattr(backend, method))
                    monkeypatch.setattr(backend, method, spy)
                    calls[f"{mount_name}/{replica}/{method}"] = spy
        assert (
            move_store.move(
                "src/item" if qualified else "item", target="dst/renamed", source_version=version, target_version="1"
            )
            == "1.0.0"
        )
        record_property("backend_calls", {key: spy.call_count for key, spy in calls.items()})
        # Baseline budgets: list_versions, has_object, fetch_metadata, pull, push, delete.
        budgets = {
            (False, False, "latest"): (2, 4, 2, 1, 1, 1),
            (False, True, "latest"): (1, 0, 2, 1, 1, 1),
            (False, False, "1"): (0, 6, 2, 1, 1, 1),
            (False, True, "1"): (0, 0, 2, 1, 1, 1),
            (True, False, "latest"): (2, 7, 6, 1, 2, 2),
            (True, True, "latest"): (1, 3, 4, 1, 2, 2),
            (True, False, "1"): (0, 9, 6, 1, 2, 2),
            (True, True, "1"): (0, 3, 4, 1, 2, 2),
        }
        methods = ("list_versions", "has_object", "fetch_metadata", "pull", "push", "delete")
        for method, limit in zip(methods, budgets[source._cached, qualified, version]):
            count = sum(spy.call_count for key, spy in calls.items() if key.endswith(f"/{method}"))
            assert count <= limit, f"Extra {method} calls: {count} > {limit}"
        # Qualified moves do not discover other mounts or preflight existence.
        if qualified:
            assert calls["temp/0/has_object"].call_count == 0
            assert calls["temp/0/list_versions"].call_count == 0
        assert move_store.load("dst/renamed", "1") == "original"


class TestPresignedDownloads:
    def test_rejects_ambiguous_read(self, tmp_path, cached_mock_registry):
        local = Registry(backend=tmp_path / "local", version_objects=True)
        remote = cached_mock_registry
        for registry in (local, remote):
            registry.save("item", b"payload", version="1.0.0")
        store = Store(mounts={"local": local, "remote": remote}, default_mount="remote")

        with pytest.raises(StoreAmbiguousObjectError):
            store.create_direct_download_url("item", version="1.0.0")

    def test_reports_no_unqualified_match(self, tmp_path):
        local = Registry(backend=tmp_path / "local", version_objects=True)
        store = Store(mounts={"local": local}, default_mount="local")

        with pytest.raises(RegistryObjectNotFound):
            store.create_direct_download_url("missing", version="1.0.0")

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
    def test_preserves_version_selection_and_url_options(
        self, download_store, monkeypatch, key, version, expected_version
    ):
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
    def test_discovery_filters_by_effective_version(self, download_store, key, version):
        store = download_store
        local = store.get_mount("local").registry
        remote = store.get_mount("remote").registry
        local.save("item", b"local", version="1.0.0")
        remote.save("item", b"remote", version="2.0.0")

        expected = remote.create_direct_download_url("item", "2.0.0")
        assert store.create_direct_download_url(key, version=version) == expected

    @pytest.mark.parametrize("cache_enabled", [False, True])
    def test_discovery_checks_each_mount_once_and_rechecks_cached_locations(
        self, download_store, monkeypatch, cache_enabled
    ):
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
    def test_qualified_signing_bypasses_discovery_even_with_duplicate_names(self, download_store, monkeypatch, version):
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

    def test_unique_local_owner_keeps_unsupported_capability_result(self, download_store, monkeypatch):
        store = download_store
        local = store.get_mount("local").registry
        local.save("item", b"local", version="1.0.0")
        store.set_default_mount("remote")
        presign = Mock(wraps=local.create_direct_download_url)
        monkeypatch.setattr(local, "create_direct_download_url", presign)

        assert store.create_direct_download_url("item", version="1.0.0") is None
        presign.assert_called_once()

    @pytest.mark.parametrize("version", [None, "1.0.0"])
    def test_no_match_does_not_issue_any_url(self, download_store, monkeypatch, version):
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

    def test_selected_signer_error_propagates_without_default_fallback(self, download_store, monkeypatch):
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

    def test_presigned_read_discovers_unique_remote_mount(self, tmp_path, cached_mock_registry, monkeypatch):
        local = Registry(backend=tmp_path / "local", version_objects=True)
        remote = cached_mock_registry
        store = Store(mounts={"local": local, "remote": remote}, default_mount="local")
        store.save("remote/item", b"value", version="1.0.0")
        expected = store.create_direct_download_url("remote/item", version="1.0.0")
        assert expected.startswith("https://example.invalid/")
        presign = Mock(wraps=remote.create_direct_download_url)
        monkeypatch.setattr(remote, "create_direct_download_url", presign)
        assert store.create_direct_download_url("item", version="1.0.0") == expected
        presign.assert_called_once()
