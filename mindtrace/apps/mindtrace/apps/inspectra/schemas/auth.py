"""Auth TaskSchemas for Inspectra."""

from mindtrace.apps.inspectra.models import (
    LoginPayload,
    RegisterPayload,
    TokenResponse,
)
from mindtrace.core import TaskSchema

LoginSchema = TaskSchema(
    name="inspectra_login",
    input_schema=LoginPayload,
    output_schema=TokenResponse,
)

RegisterSchema = TaskSchema(
    name="inspectra_register",
    input_schema=RegisterPayload,
    output_schema=TokenResponse,
)

__all__ = [
    "LoginSchema",
    "RegisterSchema",
]
