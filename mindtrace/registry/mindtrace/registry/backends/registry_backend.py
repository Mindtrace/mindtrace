from abc import abstractmethod
from pathlib import Path
from typing import Dict, List, Tuple, Union

from mindtrace.core import MindtraceABC
from mindtrace.registry.core.types import OnConflict, OpResults

# Type aliases for cleaner signatures
NameArg = Union[str, List[str]]
ConcreteVersionArg = Union[str, List[str]]  # Registry resolves versions before calling backend
VersionArg = ConcreteVersionArg  # Alias for backwards compatibility
PathArg = Union[str, Path, List[Union[str, Path]]]
MetadataArg = Union[dict, List[dict], None]


class RegistryBackend(MindtraceABC):  # pragma: no cover
    """Abstract base class for registry backends.

    Registry backends handle three concerns:
    1. Artifacts: raw files for each (name, version)
    2. Object metadata: recording what's stored, how to deserialize, and file manifest
    3. Registry-level metadata: global settings like version_objects, mutable and materializers

    The canonical invariant: an object "exists" if and only if its metadata exists.

    Key Behaviors:
    - Backend handles read and write operations.
    - Registry resolves versions before calling the backend (versions are concrete).
    - Backends implement their own concurrency control/locking; Registry may request
      locks via acquire_lock, backends decide how to handle them.

    """

    @property
    @abstractmethod
    def uri(self) -> Path:
        """The resolved base URI for the backend."""
        pass

    @abstractmethod
    def __init__(self, uri: str | Path, **kwargs):
        super().__init__(**kwargs)

    # ─────────────────────────────────────────────────────────────────────────
    # Input Preparation
    # ─────────────────────────────────────────────────────────────────────────

    def _to_list(self, val):
        """Convert scalar string to single-item list. For name/version normalization."""
        return [val] if isinstance(val, str) else list(val)

    def _prepare_inputs(self, name, version, paths, metadata):
        """Convert scalars to lists, validate all lengths match.

        Used by push/pull where all 4 inputs are required.
        Registry resolves versions before calling backend, so version must be concrete (not None).
        Scalar conversion is for test convenience.
        """
        if metadata is None:
            raise ValueError("metadata is required")
        if version is None:
            raise ValueError("version is required (Registry must resolve before calling backend)")
        names = [name] if isinstance(name, str) else list(name)
        versions = [version] if isinstance(version, str) else list(version)
        paths_list = [Path(paths)] if isinstance(paths, (str, Path)) else [Path(p) for p in paths]
        metadatas = [metadata] if isinstance(metadata, dict) else list(metadata)

        n = len(names)
        if not (len(versions) == len(paths_list) == len(metadatas) == n):
            raise ValueError(
                f"Input lengths must match: names={n}, versions={len(versions)}, "
                f"paths={len(paths_list)}, metadata={len(metadatas)}"
            )

        return names, versions, paths_list, metadatas

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def push(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        metadata: MetadataArg,
        on_conflict: str = OnConflict.SKIP,
        acquire_lock: bool = False,
    ) -> OpResults:
        """Atomically push artifacts and metadata.

        This is the primary write operation. Artifacts and metadata are committed
        together - either both succeed or both fail (with rollback).

        Registry resolves versions before calling backends; version must be concrete.

        Backends are batch-only and always return OpResults. Single-item exception
        handling is done at the Registry API surface level.

        Args:
            name: Object name(s). Single string or list.
            version: Version string(s) (concrete), or list.
            local_path: Local source directory/directories to upload from.
            metadata: Metadata dict(s) to store. Should contain at minimum:
                - "class": fully-qualified class name
                - "materializer": fully-qualified materializer class
                - "init_params": dict for materializer
                - "metadata": user metadata
                - "_files": list of relative file paths
                - "hash": content hash for verification
            on_conflict: Behavior when version exists.
                "skip": Return skipped result.
                "overwrite": Replace existing version.
            acquire_lock: Ignored by cloud backends (lock-free MVCC used).
                Kept for API compatibility. Default is False.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
            - OpResult.failed() on failure
        """
        pass

    @abstractmethod
    def pull(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        local_path: PathArg,
        acquire_lock: bool = False,
        metadata: MetadataArg = None,
    ) -> OpResults:
        """Download artifacts to local path(s).

        Uses the "_files" manifest from metadata to know exactly which
        files to download, avoiding expensive blob storage listing.

        Backends are batch-only and always return OpResults. Single-item exception
        handling is done at the Registry API surface level.

        Args:
            name: Object name(s).
            version: Version string(s).
            local_path: Local target directory/directories to download into.
            acquire_lock: Ignored by cloud backends (lock-free MVCC used).
                Kept for API compatibility. Default is False.
            metadata: Pre-fetched metadata dict(s) containing "_files" manifest.
                Required by Registry/backends; local backend accepts but doesn't use it.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        pass

    @abstractmethod
    def delete(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        acquire_lock: bool = False,
    ) -> OpResults:
        """Delete artifact(s) and metadata.

        Backends are batch-only and always return OpResults. Single-item exception
        handling is done at the Registry API surface level.

        Args:
            name: Object name(s).
            version: Version string(s).
            acquire_lock: Ignored by cloud backends (lock-free MVCC used).
                Kept for API compatibility. Default is False.

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata-Only Operations
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
        metadata: Union[dict, List[dict]],
        on_conflict: str = OnConflict.SKIP,
    ) -> "OpResults":
        """Save metadata for object version(s).

        Backends are batch-only and always return OpResults. Single-item exception
        handling is done at the Registry API surface level.

        Args:
            name: Object name(s).
            version: Version string(s).
            metadata: Metadata dict(s).
            on_conflict: Behavior when version exists.
                "skip": Return skipped result.
                "overwrite": Replace existing version.

        Returns:
            OpResults with status for each (name, version):
            - OpResult.success() on success
            - OpResult.skipped() when on_conflict="skip" and version exists
            - OpResult.overwritten() when on_conflict="overwrite" and version existed
        """
        pass

    @abstractmethod
    def fetch_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Fetch metadata for object version(s).

        This is the canonical existence check - if metadata doesn't exist,
        the object doesn't exist.

        Backends are batch-only and always return OpResults. Single-item exception
        handling is done at the Registry API surface level.

        Args:
            name: Object name(s).
            version: Version string(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success(metadata=...) on success
            - OpResult.failed() on failure (not found or error)
        """
        pass

    @abstractmethod
    def delete_metadata(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> OpResults:
        """Delete metadata for object version(s).

        Backends are batch-only and always return OpResults. Single-item exception
        handling is done at the Registry API surface level.

        Args:
            name: Object name(s).
            version: Version string(s).

        Returns:
            OpResults with OpResult for each (name, version):
            - OpResult.success() on success
            - OpResult.failed() on failure
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Registry-Level Metadata
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_registry_metadata(self, metadata: dict) -> None:
        """Save registry-level metadata.

        This stores global registry settings like version_objects.

        Args:
            metadata: Dictionary containing registry metadata.
        """
        pass

    @abstractmethod
    def fetch_registry_metadata(self) -> dict:
        """Fetch registry-level metadata.

        Returns:
            Dictionary containing registry metadata. Empty dict if none exists.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def list_objects(self) -> List[str]:
        """List all unique object names in the backend.

        Returns:
            Sorted list of object names.
        """
        pass

    @abstractmethod
    def list_versions(self, name: NameArg) -> Dict[str, List[str]]:
        """List all versions for object(s).

        Args:
            name: Object name(s).

        Returns:
            Dict mapping object names to sorted lists of version strings.
        """
        pass

    @abstractmethod
    def has_object(
        self,
        name: NameArg,
        version: ConcreteVersionArg,
    ) -> Dict[Tuple[str, str], bool]:
        """Check if object version(s) exist.

        Args:
            name: Object name(s).
            version: Version string(s).

        Returns:
            Dict mapping (name, version) tuples to existence booleans.
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Materializer Registry
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def register_materializer(
        self,
        object_class: NameArg,
        materializer_class: NameArg,
    ) -> None:
        """Register materializer(s) for object class(es).

        Args:
            object_class: Fully-qualified object class name(s).
            materializer_class: Fully-qualified materializer class name(s).
        """
        pass

    @abstractmethod
    def registered_materializers(
        self,
        object_class: Union[str, None, List[str]] = None,
    ) -> Dict[str, str]:
        """Get registered materializers.

        Args:
            object_class: If None, return all materializers.
                If string or list, return only matching object classes.

        Returns:
            Dict mapping object classes to materializer classes.
        """
        pass

    def registered_materializer(self, object_class: str) -> Union[str, None]:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        return self.registered_materializers(object_class).get(object_class, None)

    # ─────────────────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────────────────

    def validate_object_name(self, name: NameArg) -> None:
        """Validate object name(s).

        Args:
            name: Name(s) to validate.

        Raises:
            ValueError: If any name is invalid.
        """
        names = self._to_list(name)
        for n in names:
            if not n or not n.strip():
                raise ValueError("Object names cannot be empty.")
            elif "_" in n:
                raise ValueError(f"Object name '{n}' cannot contain underscores. Use colons (':') for namespacing.")
            elif "@" in n:
                raise ValueError(f"Object name '{n}' cannot contain '@'.")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Locking (protected, not part of public API)
    # ─────────────────────────────────────────────────────────────────────────

    def _acquire_internal_lock(self, key: str, lock_id: str, timeout: int, shared: bool = False) -> bool:
        """Acquire internal lock for operation.

        Override in subclass for locking support. Default is no-op.

        Supports both shared (read) and exclusive (write) locks:
        - Shared locks: Multiple readers can hold shared locks simultaneously
        - Exclusive locks: Only one writer can hold an exclusive lock, and no readers

        Args:
            key: Lock key (e.g., "{name}@{version}").
            lock_id: Unique identifier for this lock attempt.
            timeout: Lock timeout in seconds.
            shared: If True, acquire a shared (read) lock. If False, acquire an exclusive (write) lock.

        Returns:
            True if lock acquired, False otherwise.
        """
        return True  # Default: no-op

    def _release_internal_lock(self, key: str, lock_id: str) -> bool:
        """Release internal lock.

        Override in subclass for locking support. Default is no-op.

        Args:
            key: Lock key.
            lock_id: Lock ID used during acquisition.

        Returns:
            True if released, False otherwise.
        """
        return True  # Default: no-op
