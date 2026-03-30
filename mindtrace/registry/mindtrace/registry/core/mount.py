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
    GCP = "gcp"


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
class GCPMountConfig:
    """Configuration for a Google Cloud Storage-backed registry mount."""

    bucket_name: str
    project_id: str
    prefix: str | None = None
    credentials_path: str | None = None


@dataclass(frozen=True)
class NoAuth:
    """No explicit auth payload; backend resolves ambient/default auth."""

    mode: str = "none"


@dataclass(frozen=True)
class S3AccessKeyAuth:
    """Explicit S3/MinIO access-key authentication."""

    access_key: str
    secret_key: str
    mode: str = "access_key"


@dataclass(frozen=True)
class GCPServiceAccountFileAuth:
    """Explicit GCP service account file authentication."""

    path: str
    mode: str = "service_account_file"


@dataclass(frozen=True)
class Mount:
    """Declarative definition of a registry mount.

    A ``Mount`` contains enough information to construct a ``Registry`` via
    ``Registry.from_mount(...)``. It is not itself a live runtime mount.
    """

    name: str
    backend: MountBackendKind | str
    config: LocalMountConfig | S3MountConfig | GCPMountConfig
    read_only: bool = False
    is_default: bool = False
    auth: NoAuth | S3AccessKeyAuth | GCPServiceAccountFileAuth = field(default_factory=NoAuth)
    registry_options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        backend = MountBackendKind(self.backend)
        object.__setattr__(self, "backend", backend)

        if not self.name or "/" in self.name or "@" in self.name:
            raise ValueError("Invalid mount name")

        if backend is MountBackendKind.LOCAL:
            if not isinstance(self.config, LocalMountConfig):
                raise TypeError("local mounts require LocalMountConfig")
            if not isinstance(self.auth, NoAuth):
                raise TypeError("local mounts require NoAuth")

        elif backend is MountBackendKind.S3:
            if not isinstance(self.config, S3MountConfig):
                raise TypeError("s3 mounts require S3MountConfig")
            if not isinstance(self.auth, (NoAuth, S3AccessKeyAuth)):
                raise TypeError("s3 mounts require NoAuth or S3AccessKeyAuth")

        elif backend is MountBackendKind.GCP:
            if not isinstance(self.config, GCPMountConfig):
                raise TypeError("gcp mounts require GCPMountConfig")
            if not isinstance(self.auth, (NoAuth, GCPServiceAccountFileAuth)):
                raise TypeError("gcp mounts require NoAuth or GCPServiceAccountFileAuth")

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
        assert isinstance(cfg, GCPMountConfig)
        suffix = f"/{cfg.prefix.strip('/')}" if cfg.prefix else ""
        return f"gs://{cfg.bucket_name}{suffix}"
