"""Declarative mount definitions for Registry and Store."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MountBackendKind(str, Enum):
    """Supported backend kinds for declarative mounts."""

    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"


@dataclass(frozen=True)
class LocalMountConfig:
    """Configuration for a local filesystem-backed registry mount."""

    uri: str | Path


@dataclass(frozen=True)
class S3MountConfig:
    """Configuration for an S3-compatible registry mount."""

    bucket: str
    prefix: str | None = None
    endpoint: str | None = None
    secure: bool = True


@dataclass(frozen=True)
class GCSMountConfig:
    """Configuration for a Google Cloud Storage-backed registry mount."""

    bucket_name: str
    project_id: str
    prefix: str | None = None
    credentials_path: str | None = None


@dataclass(frozen=True)
class NoAuth:
    """No explicit auth required."""

    mode: str = "none"


@dataclass(frozen=True)
class AmbientAuth:
    """Use environment / ambient SDK auth resolution."""

    mode: str = "ambient"


@dataclass(frozen=True)
class S3AccessKeyAuth:
    """Explicit S3/MinIO access-key authentication."""

    access_key: str
    secret_key: str
    mode: str = "access_key"


@dataclass(frozen=True)
class GCSServiceAccountFileAuth:
    """Explicit GCS service account file authentication."""

    path: str
    mode: str = "service_account_file"


MountAuth = NoAuth | AmbientAuth | S3AccessKeyAuth | GCSServiceAccountFileAuth
MountConfig = LocalMountConfig | S3MountConfig | GCSMountConfig


@dataclass(frozen=True, init=False)
class Mount:
    """Declarative definition of a registry mount.

    A ``Mount`` contains enough information to construct a ``Registry`` via
    ``Registry.from_mount(...)``. It is not itself a live runtime mount.
    """

    name: str | None
    backend: MountBackendKind | str
    config: MountConfig
    read_only: bool = False
    is_default: bool = False
    auth: MountAuth = field(default_factory=AmbientAuth)
    registry_options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        name: str | None = None,
        backend: MountBackendKind | str | None = None,
        config: MountConfig | None = None,
        read_only: bool = False,
        is_default: bool = False,
        auth: MountAuth | None = None,
        registry_options: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "backend", backend)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "read_only", read_only)
        object.__setattr__(self, "is_default", is_default)
        object.__setattr__(self, "auth", AmbientAuth() if auth is None else auth)
        object.__setattr__(self, "registry_options", {} if registry_options is None else dict(registry_options))
        object.__setattr__(self, "metadata", {} if metadata is None else dict(metadata))
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.name is not None and not isinstance(self.name, str):
            raise TypeError("Mount name must be a string or None")
        if self.backend is None:
            raise TypeError("backend is required")
        if self.config is None:
            raise TypeError("config is required")

        backend = MountBackendKind(self.backend)
        object.__setattr__(self, "backend", backend)

        if isinstance(self.name, str) and self.name and ("/" in self.name or "@" in self.name):
            raise ValueError("Invalid mount name")

        if backend is MountBackendKind.LOCAL:
            if not isinstance(self.config, LocalMountConfig):
                raise TypeError("local mounts require LocalMountConfig")
            if not isinstance(self.auth, (NoAuth, AmbientAuth)):
                raise TypeError("local mounts require NoAuth or AmbientAuth")

        elif backend is MountBackendKind.S3:
            if not isinstance(self.config, S3MountConfig):
                raise TypeError("s3 mounts require S3MountConfig")
            if not isinstance(self.auth, (AmbientAuth, S3AccessKeyAuth)):
                raise TypeError("s3 mounts require AmbientAuth or S3AccessKeyAuth")

        elif backend is MountBackendKind.GCS:
            if not isinstance(self.config, GCSMountConfig):
                raise TypeError("gcs mounts require GCSMountConfig")
            if not isinstance(self.auth, (AmbientAuth, GCSServiceAccountFileAuth)):
                raise TypeError("gcs mounts require AmbientAuth or GCSServiceAccountFileAuth")

    @classmethod
    def from_registry(
        cls,
        registry: "Registry",
        *,
        name: str | None = None,
        read_only: bool = False,
        is_default: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "Mount":
        """Build a best-effort Mount from an existing Registry.

        For remote backends, secret material is not reconstructed; the returned
        mount uses ambient/default auth unless the backend exposes a path-based
        credential configuration.
        """
        from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend
        from mindtrace.registry.backends.s3_registry_backend import S3RegistryBackend

        backend = registry.backend
        registry_options = {
            "version_objects": registry.version_objects,
            "mutable": registry.mutable,
            "version_digits": registry.version_digits,
        }

        if backend.__class__.__name__ == "LocalRegistryBackend":
            return cls(
                name=name,
                backend=MountBackendKind.LOCAL,
                config=LocalMountConfig(uri=backend.uri),
                auth=NoAuth(),
                read_only=read_only,
                is_default=is_default,
                registry_options=registry_options,
                metadata=metadata or {},
            )

        if isinstance(backend, S3RegistryBackend):
            return cls(
                name=name,
                backend=MountBackendKind.S3,
                config=S3MountConfig(
                    bucket=backend.storage.bucket_name,
                    prefix=getattr(backend, "_prefix", "") or None,
                    endpoint=backend.storage.endpoint,
                    secure=backend.storage.secure,
                ),
                auth=AmbientAuth(),
                read_only=read_only,
                is_default=is_default,
                registry_options=registry_options,
                metadata=metadata or {},
            )

        if isinstance(backend, GCPRegistryBackend):
            return cls(
                name=name,
                backend=MountBackendKind.GCS,
                config=GCSMountConfig(
                    bucket_name=backend.gcs.bucket_name,
                    project_id=backend.config.get("MINDTRACE_GCP", {}).get("GCP_PROJECT_ID", "")
                    or backend.config.get("MINDTRACE_GCP_REGISTRY", {}).get("GCP_PROJECT_ID", ""),
                    prefix=getattr(backend, "_prefix", "") or None,
                    credentials_path=None,
                ),
                auth=AmbientAuth(),
                read_only=read_only,
                is_default=is_default,
                registry_options=registry_options,
                metadata=metadata or {},
            )

        raise TypeError(f"Unsupported registry backend type: {type(backend).__name__}")

    def display_uri(self) -> str:
        """Return a human-friendly URI-like representation for diagnostics."""
        if self.backend is MountBackendKind.LOCAL:
            cfg = self.config
            assert isinstance(cfg, LocalMountConfig)
            return str(cfg.uri)
        if self.backend is MountBackendKind.S3:
            cfg = self.config
            assert isinstance(cfg, S3MountConfig)
            suffix = f"/{cfg.prefix.strip('/')}" if cfg.prefix else ""
            return f"s3://{cfg.bucket}{suffix}"
        cfg = self.config
        assert isinstance(cfg, GCSMountConfig)
        suffix = f"/{cfg.prefix.strip('/')}" if cfg.prefix else ""
        return f"gs://{cfg.bucket_name}{suffix}"
