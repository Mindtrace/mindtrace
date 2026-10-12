"""Store mutation safety and read routing, without remote services."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mindtrace.registry import Registry, Store
from mindtrace.registry.core.exceptions import RegistryObjectNotFound


@pytest.fixture
def store(tmp_path):
    return Store(
        mounts={
            "a": Registry(backend=tmp_path / "a", version_objects=True, mutable=True),
            "b": Registry(backend=tmp_path / "b", version_objects=True, mutable=True),
        },
        default_mount="a",
    )


@pytest.mark.parametrize("operation", ["create", "commit", "cleanup"])
@pytest.mark.parametrize("qualified", [False, True], ids=["default", "qualified"])
def test_read_only_direct_writes_stop_before_backend_call(store, monkeypatch, operation, qualified):
    owner = store.get_mount("b").registry
    staged = owner.create_direct_upload_target("existing-upload")["staged_target"]
    Path(staged["path"]).write_bytes(b"owned")
    owner = store.get_mount("b").registry
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
    with pytest.raises(PermissionError):
        if operation == "create":
            store.create_direct_upload_target(key, upload_id="new-upload")
        elif operation == "commit":
            store.commit_direct_upload(key, staged_target=staged, version="1.0.0")
        else:
            store.cleanup_direct_upload_target(key, staged_target=staged)
    mutation.assert_not_called()
    assert Path(staged["path"]).read_bytes() == b"owned"
    assert not owner.has_object("item", "1.0.0")


def test_move_deletes_only_the_version_it_copied(store, monkeypatch):
    store.save("b/item", 1, version="1.0.0")
    destination = store.get_mount("a").registry
    original_save = destination.save
    writes = []

    def save_then_publish_new_source(*args, **kwargs):
        result = original_save(*args, **kwargs)
        store.save("b/item", 2, version="2.0.0")
        writes.append("2.0.0")
        return result

    monkeypatch.setattr(destination, "save", save_then_publish_new_source)
    assert store.move("b/item", target="a/item") == "1.0.0"
    assert writes == ["2.0.0"]
    assert store.load("a/item", version="1.0.0") == 1
    assert store.has_object("b/item", version="2.0.0"), "Move deleted a version it never copied"
    assert store.load("b/item", version="2.0.0") == 2
    assert not store.has_object("b/item", version="1.0.0")


def test_move_rejects_read_only_source_before_destination_write(store, monkeypatch):
    store.save("b/item", 1, version="1.0.0")
    owner = store.get_mount("b").registry
    store.remove_mount("b")
    store.add_mount(owner, name="b", read_only=True)
    destination = store.get_mount("a").registry
    write = Mock(wraps=destination.save)
    monkeypatch.setattr(destination, "save", write)
    with pytest.raises(PermissionError):
        store.move("b/item", target="a/item")
    write.assert_not_called()
    assert not store.has_object("a/item")
    assert store.load("b/item", version="1.0.0") == 1


def test_failed_move_copy_keeps_source(store, monkeypatch):
    store.save("b/item", 1, version="1.0.0")
    write = Mock(side_effect=OSError("destination unavailable"))
    monkeypatch.setattr(store.get_mount("a").registry, "save", write)
    with pytest.raises(OSError, match="destination unavailable"):
        store.move("b/item", target="a/item")
    write.assert_called_once()
    assert store.load("b/item", version="1.0.0") == 1
    assert store.list_versions("b/item") == ["1.0.0"]
    assert not store.has_object("a/item")


def test_presigned_read_discovers_unique_remote_mount(tmp_path, cached_mock_registry, monkeypatch):
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


def test_local_presigned_read_capability_and_missing_object(tmp_path):
    store = Store(mounts={"local": Registry(backend=tmp_path / "local", version_objects=True)}, default_mount="local")
    store.save("local/item", b"value")
    assert store.create_direct_download_url("local/item") is None
    with pytest.raises(RegistryObjectNotFound):
        store.create_direct_download_url("local/missing")
