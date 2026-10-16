"""Batch saves validate identities before materializing any submitted object."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from mindtrace.registry import BuiltInMaterializer, Registry, S3RegistryBackend, Store
from tests.registry_test_helpers import RejectNegativeMaterializer, RevisionedIntMaterializer
from tests.unit.mindtrace.registry.backends.test_s3_registry_backend import MockS3Handler


@pytest.fixture(params=["core", "registry", "cached", "store"])
def batch_target(request, tmp_path):
    if request.param == "cached":
        registry = request.getfixturevalue("cached_mock_registry")
    else:
        registry = Registry(backend=tmp_path / "registry", version_objects=True, mutable=True)
    target = registry
    if request.param == "core":
        target = registry._core
    elif request.param == "store":
        target = Store({"archive": registry}, default_mount="archive")
    return target, registry


@pytest.mark.parametrize("policy", ["skip", "overwrite"])
@pytest.mark.parametrize(
    "versions",
    [None, [None, "2"], ["1", None], "1", ["1", "1.0.0"], ["v1", "1.0"], ["latest", "2"]],
)
def test_invalid_repeated_names_reject_before_any_save(batch_target, monkeypatch, versions, policy):
    target, registry = batch_target
    registry.save("keep", 99, version="1")
    registry.save("item", 88, version="1")
    before = {name: registry.info(name, "1") for name in ("item", "keep")}
    materialize = Mock(wraps=BuiltInMaterializer.save)
    monkeypatch.setattr(BuiltInMaterializer, "save", materialize)
    cores = [registry._remote, registry._cache] if registry._cached else [registry._core]
    pushes = []
    for core in cores:
        push = Mock(wraps=core.backend.push)
        monkeypatch.setattr(core.backend, "push", push)
        pushes.append(push)
    repeated_versions = versions if isinstance(versions, list) else [versions, versions]
    with pytest.raises(ValueError, match="[Bb]atch|[Dd]uplicate|[Rr]epeated"):
        target.save(["unrelated", "item", "item"], [3, -1, 2], version=["1", *repeated_versions], on_conflict=policy)
    materialize.assert_not_called()
    for push in pushes:
        push.assert_not_called()
    assert sorted(registry.list_objects()) == ["item", "keep"]
    assert registry.load("keep", "1") == 99
    assert registry.load("item", "1") == 88
    assert {name: registry.info(name, "1") for name in ("item", "keep")} == before


@pytest.mark.parametrize(
    "versions, expected, latest",
    [
        (["1", "2"], ["1.0.0", "2.0.0"], 20),
        (["2", "1"], ["2.0.0", "1.0.0"], 10),
        (["1.0.0", "1.0.1"], ["1.0.0", "1.0.1"], 20),
    ],
)
def test_repeated_names_with_distinct_explicit_versions_round_trip(batch_target, versions, expected, latest):
    target, registry = batch_target
    result = target.save(["item", "item"], [10, 20], version=versions)
    assert result.results == expected
    assert result.success_count == 2
    assert result.errors == {}
    for version, value in zip(versions, [10, 20]):
        assert registry.load("item", version) == value
    assert registry.load("item", "latest") == latest


@pytest.mark.parametrize("objects", [[-1, 2], [2, -1]])
def test_valid_repeated_name_partial_success_preserves_input_order(batch_target, objects):
    target, registry = batch_target
    registry.register_materializer(int, RejectNegativeMaterializer)
    result = target.save(["item", "item"], objects, version=["1", "2"])
    expected = [None if value < 0 else f"{index + 1}.0.0" for index, value in enumerate(objects)]
    assert result.results == expected
    assert result.success_count == result.failure_count == 1
    assert len(result.errors) == 1
    assert next(iter(result.errors.values()))["error"] == "ValueError"
    for index, value in enumerate(objects):
        if value > 0:
            assert registry.load("item", str(index + 1)) == value
        else:
            assert not registry.has_object("item", str(index + 1))


@pytest.mark.parametrize("field", ["obj", "version", "metadata", "init_params"])
@pytest.mark.parametrize("versioned", [True, False])
def test_all_list_lengths_checked_before_saves(tmp_path, monkeypatch, field, versioned):
    registry = Registry(backend=tmp_path / "registry", version_objects=versioned)
    store = Store({"archive": registry}, default_mount="archive")
    materialize = Mock()
    monkeypatch.setattr(BuiltInMaterializer, "save", materialize)
    for target in (registry, store):
        options = dict(obj=[1, 2], version=["1", "2"], metadata=[{}, {}], init_params=[{}, {}])
        options[field] = options[field][:1]
        with pytest.raises(ValueError, match="length"):
            target.save(["a", "b"], **options)
    materialize.assert_not_called()
    assert registry.list_objects() == []


@pytest.mark.parametrize("versions", [None, ["1", "2"]])
def test_unversioned_repeated_names_are_rejected(tmp_path, monkeypatch, versions):
    registry = Registry(backend=tmp_path / "registry", version_objects=False)
    store = Store({"archive": registry}, default_mount="archive")
    push = Mock(wraps=registry.backend.push)
    monkeypatch.setattr(registry.backend, "push", push)
    for target in (registry, store):
        with pytest.raises(ValueError, match="[Bb]atch|[Dd]uplicate|[Rr]epeated"):
            target.save(["other", "item", "item"], [3, 1, 2], version=None if versions is None else ["1", *versions])
    push.assert_not_called()
    assert registry.list_objects() == []


@pytest.mark.parametrize("field", ["metadata", "init_params"])
@pytest.mark.parametrize("as_list", [False, True])
def test_shared_dictionaries_are_isolated_at_backend_boundary(tmp_path, monkeypatch, field, as_list):
    registry = Registry(backend=tmp_path / "registry", version_objects=True)
    store = Store({"archive": registry}, default_mount="archive")
    shared = {"nested": {"values": [1]}}
    supplied = [shared, shared] if as_list else shared
    original_push = registry.backend.push
    observed = []

    def mutate_push(names, versions, paths, metadatas, **kwargs):
        for metadata in metadatas:
            observed.append(deepcopy(metadata[field]))
            metadata[field]["nested"]["values"].append(99)
        return original_push(names, versions, paths, metadatas, **kwargs)

    monkeypatch.setattr(registry.backend, "push", mutate_push)
    for target, names in ((registry, ["a", "b"]), (store, ["c", "d"])):
        result = target.save(names, [1, 2], **{field: supplied})
        assert result.success_count == 2
        assert shared == {"nested": {"values": [1]}}
    assert observed == [{"nested": {"values": [1]}}] * 4


def test_store_shared_parameters_keep_existing_load_semantics(tmp_path):
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
def test_store_resolves_targets_before_saving_to_any_mount(tmp_path, monkeypatch, alias, versions):
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
            ["other/good", "item", f"{alias}/item"], [3, 1, 2], version=None if versions is None else ["1", *versions]
        )
    save.assert_not_called()
    assert registry.list_objects() == other.list_objects() == []


def test_store_key_versions_and_distinct_targets_are_supported(tmp_path):
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
def test_store_remote_target_identity_uses_storage_location(tmp_path, monkeypatch, second_location):
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


@pytest.mark.parametrize("digits", [1, 2, 4])
def test_identity_check_respects_configured_version_digits(tmp_path, digits):
    registry = Registry(backend=tmp_path / "registry", version_objects=True, version_digits=digits)
    normalized = ".".join(["1"] + ["0"] * (digits - 1))
    with pytest.raises(ValueError, match="Duplicate"):
        registry.save(["item", "item"], [1, 2], version=["v1", normalized])
    assert registry.list_objects() == []
    result = registry.save(["item", "item"], [1, 2], version=["1", "2"])
    assert result.success_count == 2
    assert registry.load("item", "2") == 2
