"""Connection defaults for `NatsClient`.

Sourced from `MINDTRACE_NATS__*` environment variables (nested-delimiter `__`
to match the project convention used by `CoreSettings`). All settings are
optional except the URL list, which defaults to `nats://localhost:4222`.
"""

from __future__ import annotations

import os
import socket
from typing import Annotated, List, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class NatsSettings(BaseSettings):
    """Connection defaults for `NatsClient`, env-driven via `MINDTRACE_NATS__*`."""

    model_config = SettingsConfigDict(env_prefix="MINDTRACE_NATS__", extra="ignore")

    # Servers — list, with comma-separated env support. `NoDecode` tells
    # pydantic-settings to hand the raw env string to our validator instead of
    # trying to JSON-parse it first.
    urls: Annotated[List[str], NoDecode] = Field(default_factory=lambda: ["nats://localhost:4222"])

    # Client identity.
    name: Optional[str] = None

    # Connection behavior.
    connect_timeout: float = 2.0
    max_reconnect_attempts: int = 60
    reconnect_time_wait: float = 2.0
    drain_timeout: float = 5.0
    ping_interval: float = 120.0
    max_outstanding_pings: int = 2

    # Auth.
    user: Optional[str] = None
    password: Optional[SecretStr] = None
    token: Optional[SecretStr] = None
    user_credentials: Optional[str] = None  # File path to .creds
    nkeys_seed: Optional[SecretStr] = None  # Raw seed string

    # TLS. nats-py auto-enables TLS if any URL is `tls://`, but the explicit
    # flag plus CA/cert/key paths covers the case where you connect to a
    # `nats://` URL that needs a TLS handshake. Setting `tls=True` is itself
    # the way to "require" TLS — it builds and passes an `ssl.SSLContext`,
    # which nats-py won't downgrade.
    tls: bool = False
    tls_ca_file: Optional[str] = None
    tls_cert_file: Optional[str] = None
    tls_key_file: Optional[str] = None
    tls_handshake_first: bool = False

    @field_validator("urls", mode="before")
    @classmethod
    def _split_urls(cls, v):
        """Accept comma-separated strings from env so `MINDTRACE_NATS__URLS=a,b` works."""
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
        return v

    def resolved_name(self) -> str:
        """Effective client name: explicit `name` if set, otherwise a sensible default
        that shows up in NATS server logs as `mindtrace-{PID}@{host}`."""
        if self.name:
            return self.name
        return f"mindtrace-{os.getpid()}@{socket.gethostname()}"
