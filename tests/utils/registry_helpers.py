"""Deterministic materializers and artifact assertions shared by registry tests."""

import itertools
import json
import os
from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel

from mindtrace.registry import LocalRegistryBackend, Registry, S3RegistryBackend
from mindtrace.registry.core.base_materializer import BaseMaterializer
from mindtrace.registry.core.types import OpResult, OpResults, VerifyLevel


class RevisionedIntMaterializer(BaseMaterializer):
    """A valid serializer that deliberately produces different bytes on every save."""

    revisions = itertools.count()

    def save(self, data):
        Path(self.uri, "value.json").write_text(json.dumps({"value": data, "revision": next(self.revisions)}))

    def load(self, data_type, *, offset=0):
        return json.loads(Path(self.uri, "value.json").read_text())["value"] + offset


class NoneMaterializer(BaseMaterializer):
    """Exercise successful None results without requiring builtin None registration."""

    def save(self, data):
        Path(self.uri, "none.txt").write_text("none")

    def load(self, data_type):
        assert Path(self.uri, "none.txt").read_text() == "none"
        return None


class RejectNegativeMaterializer(RevisionedIntMaterializer):
    def save(self, data):
        if data < 0:
            raise ValueError("negative input rejected by test materializer")
        super().save(data)


class FailingLoadMaterializer(RevisionedIntMaterializer):
    """Persist valid bytes but raise a real, non-absence deserialization error."""

    def load(self, data_type):
        raise ValueError("test materializer cannot decode this artifact")


def materializer_path(cls):
    return f"{cls.__module__}.{cls.__name__}"


def artifact_files(core, name, version, destination):
    """Fetch real artifact bytes independently of object materialization."""
    result = core.backend.pull(name, version, destination, metadata=core.info(name, version))
    assert result.all_ok, result
    return {str(p.relative_to(destination)): p.read_bytes() for p in destination.rglob("*") if p.is_file()}


def assert_cache_replica(registry, name, version, tmp_path):
    remote = registry._remote.info(name, version)
    cached = registry._cache.info(name, version)
    assert artifact_files(registry._cache, name, version, tmp_path / "cached") == artifact_files(
        registry._remote, name, version, tmp_path / "remote"
    ), "Cache bytes differ from the authoritative remote artifact"
    for field in ("hash", "class", "materializer", "init_params", "metadata", "_files"):
        assert cached[field] == remote[field], field


def assert_latest_snapshot_coherent(reader, monkeypatch):
    """Force a concurrent write after cache identity resolution, before remote load."""
    writer = Registry(backend=reader.backend, version_objects=True, mutable=True, use_cache=False)
    writer.save("race", 1, version="1.0.0")
    # Cross-instance TTL staleness is permitted, but must not mask this interleaving.
    monkeypatch.setattr(reader._remote, "_versions_cache_ttl", 0)
    original_load = reader._remote.load
    writes = []

    def racing_load(*args, **kwargs):
        if not writes:
            writer.save("race", 2, version="2.0.0")
            writes.append("2.0.0")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(reader._remote, "load", racing_load)
    value = reader.load("race", "latest", verify=VerifyLevel.FULL)
    assert writes == ["2.0.0"], "The race hook must actually execute"
    # Either concrete snapshot is legitimate; mislabeling its bytes is not.
    assert value in (1, 2)
    cached_versions = reader._cache.list_versions("race")
    assert cached_versions
    for version in cached_versions:
        assert reader._cache.load("race", version) == writer.load("race", version), (
            f"Cache bytes were stored under the wrong concrete version: {version}"
        )
    assert reader.load("race", "1.0.0", verify=VerifyLevel.NONE) == 1


def _stored_files(backend):
    """Read actual payload/metadata bytes without using discovery or has_object."""
    if isinstance(backend, LocalRegistryBackend):
        return {
            path.relative_to(backend.uri).as_posix(): path.read_bytes()
            for path in backend.uri.rglob("*")
            if path.is_file()
        }
    handler = backend.storage if isinstance(backend, S3RegistryBackend) else backend.gcs
    return dict(handler._objects)


def _replicas(registry):
    return [registry.backend, registry._cache.backend] if registry._cached else [registry.backend]


def _make_op_results(*results: OpResult) -> OpResults:
    """Helper to create OpResults from OpResult objects."""
    op_results = OpResults()
    for r in results:
        op_results.add(r)
    return op_results


class _SerializerMeta(type):
    """Distinguish a materializer's class from its metaclass."""


class ForeignIntMaterializer(metaclass=_SerializerMeta):
    """An importable materializer that does not inherit any Mindtrace base."""

    def __init__(self, uri: str):
        self.uri = uri

    def save(self, data: int) -> None:
        Path(self.uri, "number.txt").write_text(str(data))

    def load(self, data_type: type) -> int:
        return int(Path(self.uri, "number.txt").read_text())


class StringHolder:
    """Plain class round-tripped through the registry by a foreign materializer."""

    def __init__(self, value: str):
        self.value = value


class StringHolderMaterializer:
    """A materializer for StringHolder that does NOT inherit BaseMaterializer."""

    def __init__(self, uri: str, **_: Any):
        self.uri = uri

    def save(self, data: StringHolder) -> None:
        Path(self.uri).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(self.uri, "data.json"), "w") as f:
            json.dump({"value": data.value}, f)

    def load(self, data_type: Type[Any]) -> StringHolder:
        with open(os.path.join(self.uri, "data.json")) as f:
            payload = json.load(f)
        return StringHolder(value=payload["value"])


class _PydanticSample(BaseModel):
    """Module-scope pydantic subclass so ``Registry.load`` can re-import its class."""

    x: int
    y: str


class RelativePathBytesMaterializer(BaseMaterializer):
    """Read the requested layout without requiring the default data.txt filename."""

    def load(self, data_type, *, filename):
        return Path(self.uri, filename).read_bytes()
