"""Containment regressions; every would-be escape stays inside pytest's sandbox."""

from pathlib import Path

import pytest

from mindtrace.registry import LocalRegistryBackend, Registry


def snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*") if not p.is_symlink()
    }


@pytest.mark.parametrize("kind", ["parent", "absolute", "symlink"])
def test_object_push_cannot_escape_backend_root(tmp_path, kind):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_bytes(b"payload")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"untouched")
    if kind == "parent":
        name = "../outside/item"
    elif kind == "absolute":
        name = str(outside / "item")
    else:
        (backend.uri / "link").symlink_to(outside, target_is_directory=True)
        name = "link/item"
    before = snapshot(outside)
    try:
        result = backend.push([name], ["1.0.0"], [source], [{"_files": ["data.txt"]}]).first()
        assert result.is_error, "An escaping write must be rejected"
        assert isinstance(result.exception, ValueError)
    finally:
        assert snapshot(outside) == before, "Artifact storage escaped the registry root"


@pytest.mark.parametrize("kind", ["parent", "absolute", "symlink"])
@pytest.mark.parametrize("operation", ["pull", "delete"])
def test_object_read_and_delete_cannot_escape_backend_root(tmp_path, kind, operation):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    outside = tmp_path / "outside"
    payload = outside / "item" / "1.0.0"
    payload.mkdir(parents=True)
    (payload / "data.txt").write_bytes(b"another registry owns this")
    (outside / "sentinel").write_bytes(b"untouched")
    if kind == "parent":
        name = "../outside/item"
    elif kind == "absolute":
        name = str(outside / "item")
    else:
        (backend.uri / "link").symlink_to(outside, target_is_directory=True)
        name = "link/item"
    before = snapshot(outside)
    destination = tmp_path / "download"
    try:
        if operation == "pull":
            result = backend.pull(name, "1.0.0", destination, metadata={"_files": ["data.txt"]}).first()
        else:
            result = backend.delete(name, "1.0.0").first()
        assert result.is_error, "An escaping read/delete must be rejected"
        assert isinstance(result.exception, ValueError)
    finally:
        assert snapshot(outside) == before, "Deletion escaped the registry root"
        assert not (destination / "data.txt").exists(), "Read copied data from outside the registry root"


@pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
def test_path_load_cannot_follow_output_symlink_outside_destination(tmp_path, batch):
    reg = Registry(backend=tmp_path / "registry", version_objects=True)
    source = tmp_path / "payload.txt"
    source.write_bytes(b"payload")
    reg.save("nested/item", source, version="1.0.0")
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"untouched")
    (output / "nested").symlink_to(outside, target_is_directory=True)
    before = snapshot(outside)
    try:
        # An escaping destination must be rejected before anything is moved there.
        if batch:
            result = reg.load(["nested/item"], ["1.0.0"], output_dir=str(output))
            assert result.failure_count == 1
            assert result.success_count == 0
            assert result.errors[("nested/item", "1.0.0")]["error"] == "ValueError"
        else:
            with pytest.raises(ValueError):
                reg.load("nested/item", "1.0.0", output_dir=str(output))
    finally:
        assert snapshot(outside) == before, "Materialization escaped the requested output directory"


@pytest.mark.parametrize("kind", ["parent", "absolute", "symlink"])
def test_direct_upload_id_cannot_escape_staging_root(tmp_path, kind):
    backend = LocalRegistryBackend(uri=tmp_path / "registry")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"untouched")
    staging = backend.uri / "_direct_uploads"
    staging.mkdir()
    if kind == "parent":
        upload_id = "../../outside/attempt"
    elif kind == "absolute":
        upload_id = str(outside / "attempt")
    else:
        (staging / "link").symlink_to(outside, target_is_directory=True)
        upload_id = "link/attempt"
    before = snapshot(outside)
    try:
        with pytest.raises(ValueError):
            backend.create_direct_upload_target(upload_id)
    finally:
        assert snapshot(outside) == before, "Upload allocation escaped the staging root"


@pytest.mark.parametrize("operation", ["cleanup", "commit"])
@pytest.mark.parametrize("kind", ["foreign", "symlink"])
def test_foreign_staged_target_is_not_consumed_or_deleted(tmp_path, operation, kind):
    reg = Registry(backend=tmp_path / "registry", version_objects=True)
    outside = tmp_path / "foreign-owner"
    outside.mkdir()
    payload = outside / "data.txt"
    payload.write_bytes(b"belongs to another owner")
    (outside / "sibling.txt").write_bytes(b"must survive recursive cleanup")
    if kind == "symlink":
        staging = reg.backend.uri / "_direct_uploads"
        staging.mkdir()
        (staging / "foreign-link").symlink_to(outside, target_is_directory=True)
        payload = staging / "foreign-link" / "data.txt"
    target = {"kind": "local_file", "path": str(payload)}
    before = snapshot(outside)
    try:
        if operation == "cleanup":
            assert reg.cleanup_direct_upload_target(target) is False
        else:
            with pytest.raises(ValueError):
                reg.commit_direct_upload("item", staged_target=target, version="1.0.0")
        assert not reg.has_object("item", "1.0.0")
    finally:
        assert outside.is_dir(), "Cleanup removed a directory it does not own"
        assert snapshot(outside) == before


@pytest.mark.parametrize("absolute", [False, True], ids=["parent", "absolute"])
def test_materialize_from_bytes_contains_relative_path(tmp_path, monkeypatch, absolute):
    reg = Registry(backend=tmp_path / "registry")
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(reg._core, "_artifact_store_path", staging)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"untouched")
    # core creates <staging>/<temporary>/staged; three parent hops reach tmp_path.
    relative_path = str(outside / "escaped.txt") if absolute else "../../../outside/escaped.txt"
    before = snapshot(outside)
    try:
        with pytest.raises(ValueError):
            reg.materialize_from_bytes(
                b"attempt",
                object_class="builtins.bytes",
                materializer="mindtrace.registry.archivers.builtin_materializers.BytesMaterializer",
                relative_path=relative_path,
            )
    finally:
        assert snapshot(outside) == before, "Materialization wrote outside its temporary directory"


def test_valid_local_direct_upload_lifecycle(tmp_path):
    """Positive ownership control: containment must not disable ordinary uploads."""
    reg = Registry(backend=tmp_path / "registry", version_objects=True)
    target = reg.create_direct_upload_target("owned-upload")["staged_target"]
    Path(target["path"]).write_bytes(b"owned")
    assert reg.commit_direct_upload("item", staged_target=target, version="1.0.0") == "1.0.0"
    assert reg.load("item", "1.0.0") == b"owned"
    assert not Path(target["path"]).exists()
