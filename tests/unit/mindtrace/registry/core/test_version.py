from tempfile import TemporaryDirectory

import pytest

from mindtrace.registry import Mount, Registry
from mindtrace.registry.core.types import Version


def test_version_normalization_with_fixed_digits():
    assert Version("1", digits=3) == Version("1.0", digits=3)
    assert Version("1.0", digits=3) == Version("1.0.0", digits=3)
    assert str(Version("1", digits=3)) == "1.0.0"


def test_version_rejects_more_components_than_digits():
    with pytest.raises(ValueError, match="between 1 and 3"):
        Version("1.0.0.0", digits=3)


def test_version_bump_increments_last_component():
    assert str(Version("1", digits=2).bump()) == "1.1"
    assert str(Version("1.0.9", digits=3).bump()) == "1.0.10"


def test_registry_uses_fixed_width_version_canonicalization():
    with TemporaryDirectory() as temp_dir:
        registry = Registry(backend=temp_dir, version_objects=True, version_digits=3)

        registry.save("my:object", 42, version="1")
        assert registry.has_object("my:object", "1")
        assert registry.has_object("my:object", "1.0")
        assert registry.has_object("my:object", "1.0.0")

        with pytest.raises(ValueError, match="between 1 and 3"):
            registry.save("my:object", 43, version="1.0.0.0")


def test_registry_digits_one_rejects_dotted_input():
    with TemporaryDirectory() as temp_dir:
        registry = Registry(backend=temp_dir, version_objects=True, version_digits=1)
        registry.save("my:object", 42, version="1")

        with pytest.raises(ValueError, match="between 1 and 1"):
            registry.save("my:object", 43, version="1.0")

        with pytest.raises(ValueError, match="between 1 and 1"):
            registry.save("my:object", 44, version="1.0.0")


def test_registry_version_digits_is_immutable_once_created():
    with TemporaryDirectory() as temp_dir:
        Registry(backend=temp_dir, version_objects=True, version_digits=1)

        # Matching config is fine
        Registry(backend=temp_dir, version_objects=True, version_digits=1)

        # Mismatched version_digits should fail
        with pytest.raises(ValueError, match="Version digits conflict"):
            Registry(backend=temp_dir, version_objects=True, version_digits=3)


# ─────────────────────────────────────────────────────────────────────────────
# version_scheme="exact"
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def exact_registry(tmp_path):
    return Registry(backend=tmp_path, version_objects=True, version_scheme="exact")


@pytest.mark.parametrize("version", ["2.05", "v2.5", "V2", "1", "2024-05-01", "rc_1", "a.b-c_d"])
def test_exact_registry_keeps_version_as_given(exact_registry, version):
    assert exact_registry.save("model", "value", version=version) == version
    assert exact_registry.list_versions("model") == [version]
    assert exact_registry.load("model", version) == "value"


@pytest.mark.parametrize("version", ["", " ", "1 2", "a/b", "a@b", ".", "..", ".hidden", "-1", "_x", "1:2"])
def test_exact_registry_rejects_unsafe_versions(exact_registry, version):
    with pytest.raises(ValueError):
        exact_registry.save("model", "value", version=version)
    assert exact_registry.list_versions("model") == []


def test_exact_registry_versions_that_look_equal_numerically_are_distinct(exact_registry):
    exact_registry.save("model", "a", version="2.05")
    exact_registry.save("model", "b", version="2.5")

    assert exact_registry.load("model", "2.05") == "a"
    assert exact_registry.load("model", "2.5") == "b"
    assert not exact_registry.has_object("model", "2.5.0")


def test_exact_registry_sorts_versions_naturally(exact_registry):
    for version in ["3.01", "2.1", "9", "2.2", "2.01", "2.10", "10"]:
        exact_registry.save("model", version, version=version)

    assert exact_registry.list_versions("model") == ["2.01", "2.1", "2.2", "2.10", "3.01", "9", "10"]
    assert exact_registry.load("model") == "10"


def test_exact_registry_save_without_version_raises(exact_registry):
    with pytest.raises(ValueError):
        exact_registry.save("model", 1)
    assert exact_registry.list_versions("model") == []


def test_exact_registry_batch_save_and_load(exact_registry):
    result = exact_registry.save(["a", "b"], [1, 2], version=["4", "2.05"])
    assert result.results == ["4", "2.05"]
    assert exact_registry.load(["a", "b"], ["4", "2.05"]).results == [1, 2]


def test_exact_scheme_requires_version_objects(tmp_path):
    with pytest.raises(ValueError):
        Registry(backend=tmp_path, version_scheme="exact")


def test_unknown_version_scheme_raises(tmp_path):
    with pytest.raises(ValueError):
        Registry(backend=tmp_path, version_objects=True, version_scheme="semver")


def test_version_scheme_is_kept_when_reopened(tmp_path):
    Registry(backend=tmp_path, version_objects=True, version_scheme="exact")

    reopened = Registry(backend=tmp_path)
    assert reopened.version_scheme == "exact"
    reopened.save("model", "value", version="2.05")
    assert reopened.list_versions("model") == ["2.05"]

    with pytest.raises(ValueError):
        Registry(backend=tmp_path, version_objects=True, version_scheme="numeric")


def test_version_scheme_defaults_to_numeric_and_is_kept(tmp_path):
    registry = Registry(backend=tmp_path, version_objects=True)
    assert registry.version_scheme == "numeric"
    assert registry.save("model", "value", version="2.05") == "2.5.0"

    with pytest.raises(ValueError):
        Registry(backend=tmp_path, version_scheme="exact")


def test_registry_created_before_version_scheme_opens_as_numeric_without_changes(tmp_path):
    backend = Registry(backend=tmp_path, version_objects=True).backend
    legacy_metadata = {k: v for k, v in backend.fetch_registry_metadata().items() if k != "version_scheme"}
    backend.save_registry_metadata(legacy_metadata)

    reopened = Registry(backend=tmp_path)
    assert reopened.version_scheme == "numeric"
    assert reopened.backend.fetch_registry_metadata() == legacy_metadata

    with pytest.raises(ValueError):
        Registry(backend=tmp_path, version_scheme="exact")


@pytest.mark.parametrize("scheme", ["numeric", "exact"])
def test_version_scheme_survives_mount_round_trip(tmp_path, scheme):
    registry = Registry(backend=tmp_path, version_objects=True, version_scheme=scheme)
    assert Registry.from_mount(Mount.from_registry(registry)).version_scheme == scheme
