"""Inspectra API routes: one module per domain (auth, organizations, users)."""

from mindtrace.apps.inspectra.routes import auth, organizations, users

__all__ = ["auth", "organizations", "users"]
