"""Local filesystem-based registry backend.

All object directories and registry files are stored under a configurable base directory.
"""

import json
import os
import platform
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Tuple, Union

import yaml

# Import appropriate locking mechanism based on OS
if platform.system() == "Windows":
    import msvcrt

    fcntl = None
else:
    import fcntl

    msvcrt = None

from mindtrace.registry.backends.registry_backend import (
    MetadataArg,
    NameArg,
    PathArg,
    RegistryBackend,
    VersionArg,
)
from mindtrace.registry.core.exceptions import (
    LockAcquisitionError,
    RegistryObjectNotFound,
    RegistryVersionConflict,
)


class LocalRegistryBackend(RegistryBackend):
    """A simple local filesystem-based registry backend.

    All object directories and registry files are stored under a configurable base directory.
    Provides atomic operations with rollback support.
    """

    def __init__(self, uri: str | Path, **kwargs):
        """Initialize the LocalRegistryBackend.

        Args:
            uri: The base directory path where all object files and metadata will be stored.
                Supports "file://" URI scheme which will be automatically stripped.
            **kwargs: Additional keyword arguments for the RegistryBackend.
        """
        if isinstance(uri, str) and uri.startswith("file://"):
            uri = uri[len("file://") :]
        super().__init__(uri=uri, **kwargs)
        self._uri = Path(uri).expanduser().resolve()
        self._uri.mkdir(parents=True, exist_ok=True)
        self._metadata_path = self._uri / "registry_metadata.json"
        self.logger.debug(f"Initializing LocalBackend with uri: {self._uri}")

    @property
    def uri(self) -> Path:
        """The resolved base directory path for the backend."""
        return self._uri

    @property
    def metadata_path(self) -> Path:
        """The resolved metadata file path for the backend."""
        return self._metadata_path

    # ─────────────────────────────────────────────────────────────────────────
    # Path Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _full_path(self, remote_key: str) -> Path:
        """Convert a remote key to a full filesystem path."""
        return self.uri / remote_key

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key."""
        return f"{name}/{version}"

    def _object_metadata_path(self, name: str, version: str) -> Path:
        """Generate the metadata file path for an object version."""
        return self.uri / f"_meta_{name.replace(':', '_')}@{version}.yaml"

    def _object_metadata_prefix(self, name: str) -> str:
        """Generate the metadata file prefix for listing versions of an object."""
        return f"_meta_{name.replace(':', '_')}@"

    def _lock_path(self, key: str) -> Path:
        """Get the path for a lock file."""
        return self._full_path(f"_lock_{key}")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Locking
    # ─────────────────────────────────────────────────────────────────────────

    def _acquire_file_lock(self, file_obj) -> bool:
        """Acquire a file lock using the appropriate mechanism for the OS."""
        try:
            if platform.system() == "Windows":
                assert msvcrt is not None
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            else:
                assert fcntl is not None
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
        except (IOError, OSError):
            return False

    def _release_file_lock(self, file_obj) -> None:
        """Release a file lock using the appropriate mechanism for the OS."""
        try:
            if platform.system() == "Windows":
                assert msvcrt is not None
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                assert fcntl is not None
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError) as e:
            self.logger.warning(f"Error releasing file lock: {e}")

    def _acquire_internal_lock(self, key: str, lock_id: str, timeout: int) -> bool:
        """Acquire internal lock using atomic file operations."""
        lock_path = self._lock_path(key)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Try atomic file creation with O_EXCL
            if platform.system() == "Windows":
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            else:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)

            # File created - we have the lock
            with os.fdopen(fd, "r+") as f:
                metadata = {"lock_id": lock_id, "expires_at": time.time() + timeout}
                f.write(json.dumps(metadata))
                f.flush()
                os.fsync(f.fileno())
                return True

        except FileExistsError:
            # Check if existing lock is expired
            try:
                with open(lock_path, "r") as f:
                    content = f.read().strip()
                    if not content:
                        lock_path.unlink()
                        return self._acquire_internal_lock(key, lock_id, timeout)
                    meta = json.loads(content)

                if time.time() > meta.get("expires_at", 0):
                    # Expired - remove and retry
                    lock_path.unlink()
                    return self._acquire_internal_lock(key, lock_id, timeout)
                return False
            except (json.JSONDecodeError, IOError, FileNotFoundError):
                return False
        except Exception as e:
            self.logger.error(f"Error acquiring lock for {key}: {e}")
            return False

    def _release_internal_lock(self, key: str, lock_id: str) -> bool:
        """Release internal lock by removing the lock file."""
        lock_path = self._lock_path(key)

        try:
            if not lock_path.exists():
                return True

            with open(lock_path, "r") as f:
                meta = json.loads(f.read().strip())
                if meta.get("lock_id") != lock_id:
                    return False

            lock_path.unlink()
            return True
        except Exception as e:
            self.logger.error(f"Error releasing lock for {key}: {e}")
            return False

    @contextmanager
    def _internal_lock(self, key: str, timeout: int = 30):
        """Context manager for internal locking."""
        lock_id = str(uuid.uuid4())
        if not self._acquire_internal_lock(key, lock_id, timeout):
            raise LockAcquisitionError(f"Cannot acquire lock for {key}")
        try:
            yield
        finally:
            self._release_internal_lock(key, lock_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations (atomic)
    # ─────────────────────────────────────────────────────────────────────────

    def push(
        self,
        name: NameArg,
        version: VersionArg,
        local_path: PathArg,
        metadata: MetadataArg = None,
    ) -> Dict[Tuple[str, str], str]:
        """Atomically push artifacts and metadata with rollback on failure."""
        entries = self._normalize_inputs(name, version, local_path, metadata)
        results: Dict[Tuple[str, str], str] = {}

        for obj_name, obj_version, obj_path, obj_meta in entries:
            self.validate_object_name(obj_name)

            with self._internal_lock(f"{obj_name}@push"):
                # Resolve version (auto-increment if None)
                resolved_version = self._resolve_version(obj_name, obj_version)

                artifact_dst = self._full_path(self._object_key(obj_name, resolved_version))
                meta_path = self._object_metadata_path(obj_name, resolved_version)

                # Check for existing version
                if meta_path.exists():
                    raise RegistryVersionConflict(f"Object {obj_name}@{resolved_version} already exists.")

                try:
                    # 1. Copy artifacts
                    shutil.copytree(obj_path, artifact_dst, dirs_exist_ok=True)

                    # 2. Write metadata (commit point)
                    if obj_meta is not None:
                        # Add path to metadata
                        obj_meta = dict(obj_meta)
                        obj_meta["path"] = str(artifact_dst)

                        with open(meta_path, "w") as f:
                            yaml.safe_dump(obj_meta, f)

                    results[(obj_name, resolved_version)] = "ok"

                except Exception as e:
                    # Rollback: remove artifacts and metadata
                    if artifact_dst.exists():
                        shutil.rmtree(artifact_dst, ignore_errors=True)
                    if meta_path.exists():
                        meta_path.unlink(missing_ok=True)
                    raise RuntimeError(f"Push failed for {obj_name}@{resolved_version}: {e}") from e

        return results

    def pull(
        self,
        name: NameArg,
        version: NameArg,
        local_path: PathArg,
    ) -> None:
        """Download artifacts to local path(s)."""
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        paths = self._normalize_paths(local_path, len(names))

        if len(names) != len(versions) or len(names) != len(paths):
            raise ValueError("Input list lengths must match")

        for obj_name, obj_version, dest_path in zip(names, versions, paths):
            src = self._full_path(self._object_key(obj_name, obj_version))

            if not src.exists():
                raise RegistryObjectNotFound(f"Object {obj_name}@{obj_version} not found.")

            self.logger.debug(f"Downloading from {src} to {dest_path}")
            shutil.copytree(src, dest_path, dirs_exist_ok=True)

    def delete(
        self,
        name: NameArg,
        version: NameArg,
    ) -> None:
        """Delete artifact(s) and metadata."""
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        for obj_name, obj_version in zip(names, versions):
            with self._internal_lock(f"{obj_name}@{obj_version}"):
                # Delete artifacts
                target = self._full_path(self._object_key(obj_name, obj_version))
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)

                # Delete metadata
                meta_path = self._object_metadata_path(obj_name, obj_version)
                if meta_path.exists():
                    meta_path.unlink()

                # Cleanup empty parent directories
                parent = target.parent
                if parent.exists() and not any(parent.iterdir()):
                    try:
                        parent.rmdir()
                    except Exception:
                        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata-Only Operations
    # ─────────────────────────────────────────────────────────────────────────

    def save_metadata(
        self,
        name: NameArg,
        version: NameArg,
        metadata: Union[dict, List[dict]],
    ) -> None:
        """Save metadata only (insert-only)."""
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)
        metadatas = self._normalize_metadata(metadata, len(names))

        if not (len(names) == len(versions) == len(metadatas)):
            raise ValueError("Input list lengths must match")

        for obj_name, obj_version, obj_meta in zip(names, versions, metadatas):
            self.validate_object_name(obj_name)
            meta_path = self._object_metadata_path(obj_name, obj_version)

            if meta_path.exists():
                raise RegistryVersionConflict(f"Object {obj_name}@{obj_version} already exists.")

            with open(meta_path, "w") as f:
                yaml.safe_dump(obj_meta, f)

    def fetch_metadata(
        self,
        name: NameArg,
        version: NameArg,
    ) -> Dict[Tuple[str, str], dict]:
        """Fetch metadata for object version(s)."""
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], dict] = {}

        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)

            try:
                with open(meta_path, "r") as f:
                    meta = yaml.safe_load(f)

                if meta is None:
                    continue  # Skip empty/corrupted files

                # Add path to metadata
                object_key = self._object_key(obj_name, obj_version)
                meta["path"] = str(self._full_path(object_key))

                results[(obj_name, obj_version)] = meta
            except FileNotFoundError:
                continue  # Skip missing entries

        return results

    def delete_metadata(
        self,
        name: NameArg,
        version: NameArg,
    ) -> None:
        """Delete metadata for object version(s)."""
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)
            if meta_path.exists():
                meta_path.unlink()

    # ─────────────────────────────────────────────────────────────────────────
    # Registry-Level Metadata
    # ─────────────────────────────────────────────────────────────────────────

    def save_registry_metadata(self, metadata: dict) -> None:
        """Save registry-level metadata."""
        with open(self._metadata_path, "w") as f:
            json.dump(metadata, f)

    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata."""
        try:
            if not self._metadata_path.exists():
                return {}
            with open(self._metadata_path, "r") as f:
                return json.load(f)
        except Exception as e:
            self.logger.debug(f"Could not load registry metadata: {e}")
            return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

    def list_objects(self) -> List[str]:
        """List all objects in the backend."""
        objects = set()
        for meta_file in self.uri.glob("_meta_*.yaml"):
            name_part = meta_file.stem.split("@")[0].replace("_meta_", "")
            name = name_part.replace("_", ":")
            objects.add(name)
        return sorted(list(objects))

    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        """List all versions for object(s)."""
        names = self._normalize_to_list(name)
        results: Dict[str, List[str]] = {}

        for obj_name in names:
            prefix = self._object_metadata_prefix(obj_name)
            versions = []

            for meta_file in self.uri.glob(f"{prefix}*.yaml"):
                version = meta_file.name[len(prefix) : -5]  # Remove prefix and .yaml
                versions.append(version)

            # Semantic sort
            def version_key(v):
                try:
                    return [int(x) for x in v.split(".")]
                except ValueError:
                    return [0]

            results[obj_name] = sorted(versions, key=version_key)

        return results

    def has_object(
        self,
        name: NameArg,
        version: NameArg,
    ) -> Dict[Tuple[str, str], bool]:
        """Check if object version(s) exist."""
        names = self._normalize_to_list(name)
        versions = self._normalize_to_list(version)

        if len(names) != len(versions):
            raise ValueError("name and version list lengths must match")

        results: Dict[Tuple[str, str], bool] = {}

        for obj_name, obj_version in zip(names, versions):
            meta_path = self._object_metadata_path(obj_name, obj_version)
            results[(obj_name, obj_version)] = meta_path.exists()

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Materializer Registry
    # ─────────────────────────────────────────────────────────────────────────

    def register_materializer(
        self,
        object_class: NameArg,
        materializer_class: NameArg,
    ) -> None:
        """Register materializer(s) for object class(es)."""
        obj_classes = self._normalize_to_list(object_class)
        mat_classes = self._normalize_to_list(materializer_class)

        if len(obj_classes) != len(mat_classes):
            raise ValueError("object_class and materializer_class list lengths must match")

        metadata = self.fetch_registry_metadata()
        if "materializers" not in metadata:
            metadata["materializers"] = {}

        for obj_cls, mat_cls in zip(obj_classes, mat_classes):
            metadata["materializers"][obj_cls] = mat_cls

        self.save_registry_metadata(metadata)
        self.logger.debug(f"Registered {len(obj_classes)} materializer(s)")

    def registered_materializers(
        self,
        object_class: Union[str, None, List[str]] = None,
    ) -> Dict[str, str]:
        """Get registered materializers."""
        metadata = self.fetch_registry_metadata()
        all_materializers = metadata.get("materializers", {})

        if object_class is None:
            return all_materializers

        if isinstance(object_class, str):
            obj_classes = [object_class]
        else:
            obj_classes = object_class

        return {k: v for k, v in all_materializers.items() if k in obj_classes}

    # ─────────────────────────────────────────────────────────────────────────
    # Legacy Support (for overwrite operations)
    # ─────────────────────────────────────────────────────────────────────────

    def overwrite(self, source_name: str, source_version: str, target_name: str, target_version: str):
        """Overwrite an object (atomic move from source to target)."""
        source_path = self._full_path(self._object_key(source_name, source_version))
        target_path = self._full_path(self._object_key(target_name, target_version))
        source_meta_path = self._object_metadata_path(source_name, source_version)
        target_meta_path = self._object_metadata_path(target_name, target_version)

        self.logger.debug(f"Overwriting {target_name}@{target_version} with {source_name}@{source_version}")

        try:
            # Remove target if exists
            if target_path.exists():
                shutil.rmtree(target_path)
            if target_meta_path.exists():
                target_meta_path.unlink()

            # Move source to target
            source_path.rename(target_path)

            if source_meta_path.exists():
                source_meta_path.rename(target_meta_path)

            # Update metadata path
            if target_meta_path.exists():
                with open(target_meta_path, "r") as f:
                    metadata = yaml.safe_load(f)
                metadata["path"] = str(target_path)
                with open(target_meta_path, "w") as f:
                    yaml.dump(metadata, f)

            self.logger.debug(f"Successfully overwrote {target_name}@{target_version}")

        except Exception as e:
            self.logger.error(f"Error during overwrite operation: {e}")
            if target_path.exists() and not source_path.exists():
                shutil.rmtree(target_path)
            raise
