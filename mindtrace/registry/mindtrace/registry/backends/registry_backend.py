"""Abstract base class for registry backends.

Registry backends handle three concerns:
1. Artifacts: raw files for each (name, version)
2. Object metadata: recording what's stored, how to deserialize, and file manifest
3. Registry-level metadata: global settings like version_objects and materializers

The canonical invariant: an object "exists" if and only if its metadata exists.
"""

from abc import abstractmethod
from pathlib import Path
from typing import Dict, List, Tuple, Union

from mindtrace.core import MindtraceABC

# Type aliases for cleaner signatures
NameArg = Union[str, List[str]]
VersionArg = Union[str, None, List[Union[str, None]]]
PathArg = Union[str, Path, List[Union[str, Path]]]
MetadataArg = Union[dict, List[dict], None]


class RegistryBackend(MindtraceABC):  # pragma: no cover
    """Abstract base class for registry backends.

    Registry backends handle three concerns:
    1. Artifacts: raw files for each (name, version)
    2. Object metadata: recording what's stored, how to deserialize, and file manifest
    3. Registry-level metadata: global settings like version_objects and materializers

    The canonical invariant: an object "exists" if and only if its metadata exists.

    Key design principles:
    - Backend handles locking internally (not exposed to Registry)
    - push() with metadata is atomic (artifacts + metadata succeed/fail together)
    - Version auto-increment happens atomically in backend when version=None
    - Single/batch operations unified via str|list parameter types
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
    # Input Normalization Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _normalize_to_list(self, value: Union[str, List[str]], name: str = "value") -> List[str]:
        """Convert single value or list to list."""
        if isinstance(value, str):
            return [value]
        return list(value)

    def _normalize_versions(self, version: VersionArg, length: int) -> List[Union[str, None]]:
        """Normalize version argument to list matching expected length."""
        if version is None or isinstance(version, str):
            return [version] * length
        return list(version)

    def _normalize_paths(self, local_path: PathArg, length: int) -> List[Path]:
        """Normalize path argument to list of Paths."""
        if isinstance(local_path, (str, Path)):
            return [Path(local_path)] * length
        return [Path(p) for p in local_path]

    def _normalize_metadata(self, metadata: MetadataArg, length: int) -> List[Union[dict, None]]:
        """Normalize metadata argument to list."""
        if metadata is None:
            return [None] * length
        if isinstance(metadata, dict):
            return [metadata] * length
        return list(metadata)

    def _normalize_inputs(
        self,
        name: NameArg,
        version: VersionArg,
        local_path: PathArg | None = None,
        metadata: MetadataArg = None,
    ) -> List[Tuple[str, Union[str, None], Union[Path, None], Union[dict, None]]]:
        """Normalize all inputs to list of tuples for processing.

        Returns:
            List of (name, version, path, metadata) tuples
        """
        names = self._normalize_to_list(name, "name")
        n = len(names)

        versions = self._normalize_versions(version, n)
        paths = self._normalize_paths(local_path, n) if local_path is not None else [None] * n
        metadatas = self._normalize_metadata(metadata, n)

        if not (len(names) == len(versions) == len(paths) == len(metadatas)):
            raise ValueError(
                f"Input list lengths must match: names={len(names)}, "
                f"versions={len(versions)}, paths={len(paths)}, metadata={len(metadatas)}"
            )

        return list(zip(names, versions, paths, metadatas))

    # ─────────────────────────────────────────────────────────────────────────
    # Artifact + Metadata Operations (atomic)
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def push(
        self,
        name: NameArg,
        version: VersionArg,
        local_path: PathArg,
        metadata: MetadataArg = None,
        on_conflict: str = "error",
    ) -> Dict[Tuple[str, str], str]:
        """Atomically push artifacts and metadata.

        This is the primary write operation. Artifacts and metadata are committed
        together - either both succeed or both fail (with rollback).

        If version is None, auto-increments to next version atomically.
        Backend handles locking internally.

        Args:
            name: Object name(s). Single string or list.
            version: Version string(s), None for auto-increment, or list.
            local_path: Local source directory/directories to upload from.
            metadata: Metadata dict(s) to store. Should contain at minimum:
                - "class": fully-qualified class name
                - "materializer": fully-qualified materializer class
                - "init_params": dict for materializer
                - "metadata": user metadata
                - "_files": list of relative file paths
                - "hash": content hash for verification
            on_conflict: Behavior when version exists. "error" raises RegistryVersionConflict,
                "skip" silently skips. Default is "error".

        Returns:
            Dict mapping (name, resolved_version) to "ok" or "skipped".

        Raises:
            RegistryVersionConflict: If version already exists and on_conflict="error".
            ValueError: If inputs are invalid.
        """
        pass

    @abstractmethod
    def pull(
        self,
        name: NameArg,
        version: NameArg,
        local_path: PathArg,
    ) -> None:
        """Download artifacts to local path(s).

        Uses the "_files" manifest from metadata to know exactly which
        files to download, avoiding expensive blob storage listing.

        No locking needed - metadata is the commit point, so reads are
        always consistent.

        Args:
            name: Object name(s).
            version: Version string(s).
            local_path: Local target directory/directories to download into.

        Raises:
            RegistryObjectNotFound: If object doesn't exist.
        """
        pass

    @abstractmethod
    def delete(
        self,
        name: NameArg,
        version: NameArg,
    ) -> None:
        """Delete artifact(s) and metadata.

        Backend handles locking internally.

        Args:
            name: Object name(s).
            version: Version string(s).
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata-Only Operations
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_metadata(
        self,
        name: NameArg,
        version: NameArg,
        metadata: Union[dict, List[dict]],
    ) -> None:
        """Save metadata only (insert-only, raises on conflict).

        This is separate from push() for cases where metadata needs to be
        updated independently of artifacts.

        Args:
            name: Object name(s).
            version: Version string(s).
            metadata: Metadata dict(s).

        Raises:
            RegistryVersionConflict: If (name, version) already exists.
        """
        pass

    @abstractmethod
    def fetch_metadata(
        self,
        name: NameArg,
        version: NameArg,
    ) -> Dict[Tuple[str, str], dict]:
        """Fetch metadata for object version(s).

        This is the canonical existence check - if metadata doesn't exist,
        the object doesn't exist.

        Args:
            name: Object name(s).
            version: Version string(s).

        Returns:
            Dict mapping (name, version) tuples to their metadata dicts.
            Missing entries are omitted from the result.
        """
        pass

    @abstractmethod
    def delete_metadata(
        self,
        name: NameArg,
        version: NameArg,
    ) -> None:
        """Delete metadata for object version(s).

        Args:
            name: Object name(s).
            version: Version string(s).
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
        version: NameArg,
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
        names = self._normalize_to_list(name, "name")
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

    def _acquire_internal_lock(self, key: str, lock_id: str, timeout: int) -> bool:
        """Acquire internal lock for operation.

        Override in subclass for locking support. Default is no-op.

        Args:
            key: Lock key (e.g., "{name}@push").
            lock_id: Unique identifier for this lock attempt.
            timeout: Lock timeout in seconds.

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

    # ─────────────────────────────────────────────────────────────────────────
    # Version Resolution (protected)
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_version(self, name: str, version: Union[str, None]) -> str:
        """Resolve version, auto-incrementing if None.

        Args:
            name: Object name.
            version: Version string or None for auto-increment.

        Returns:
            Resolved version string.
        """
        if version is not None:
            return version

        # Auto-increment: find latest and increment
        versions_dict = self.list_versions(name)
        versions = versions_dict.get(name, [])

        if not versions:
            return "1"

        # Filter temporary versions
        versions = [v for v in versions if not v.startswith("__temp__")]
        if not versions:
            return "1"

        # Semantic sort and increment
        def version_key(v):
            try:
                return [int(x) for x in v.split(".")]
            except ValueError:
                return [0]

        latest = max(versions, key=version_key)
        components = latest.split(".")
        components[-1] = str(int(components[-1]) + 1)
        return ".".join(components)
