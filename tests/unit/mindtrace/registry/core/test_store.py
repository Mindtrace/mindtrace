from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import Registry, Store
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    StoreAmbiguousObjectError,
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
