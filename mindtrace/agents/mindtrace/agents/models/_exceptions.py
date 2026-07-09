"""Provider-neutral model exceptions.

Each chat model maps its SDK's exceptions onto this hierarchy, so callers can
catch e.g. ``ModelRateLimitError`` without knowing which provider is behind the
``Model``. The original SDK exception is always preserved as ``__cause__``.

This module deliberately imports no provider SDK: ``map_provider_error`` looks
the SDK's exception classes up by name, which works because the ``openai`` and
``anthropic`` SDKs share the same exception taxonomy.
"""

from __future__ import annotations

from types import ModuleType


class ModelError(Exception):
    """Base class for all model/provider errors."""

    def __init__(self, message: str, *, provider_name: str | None = None) -> None:
        super().__init__(message)
        self.provider_name = provider_name


class ModelConnectionError(ModelError):
    """The provider could not be reached."""


class ModelTimeoutError(ModelError):
    """The request timed out."""


class ModelAPIError(ModelError):
    """The provider returned an error response."""

    def __init__(
        self,
        message: str,
        *,
        provider_name: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, provider_name=provider_name)
        self.status_code = status_code


class ModelAuthenticationError(ModelAPIError):
    """Invalid or missing credentials, or insufficient permissions (401/403)."""


class ModelRateLimitError(ModelAPIError):
    """The provider throttled the request (429)."""


class ModelBadRequestError(ModelAPIError):
    """The provider rejected the request as invalid (400/422)."""


def map_provider_error(error: Exception, sdk: ModuleType, provider_name: str) -> ModelError | None:
    """Map an SDK exception to the neutral hierarchy; None if not an SDK error.

    Order matters: in both SDKs ``APITimeoutError`` subclasses
    ``APIConnectionError``, and the specific status errors subclass
    ``APIStatusError``.
    """
    message = str(error)
    if isinstance(error, sdk.APITimeoutError):
        return ModelTimeoutError(message, provider_name=provider_name)
    if isinstance(error, sdk.APIConnectionError):
        return ModelConnectionError(message, provider_name=provider_name)
    if isinstance(error, sdk.APIStatusError):
        status_code = error.status_code
        if isinstance(error, sdk.RateLimitError):
            cls: type[ModelAPIError] = ModelRateLimitError
        elif isinstance(error, (sdk.AuthenticationError, sdk.PermissionDeniedError)):
            cls = ModelAuthenticationError
        elif isinstance(error, (sdk.BadRequestError, sdk.UnprocessableEntityError)):
            cls = ModelBadRequestError
        else:
            cls = ModelAPIError
        return cls(message, provider_name=provider_name, status_code=status_code)
    if isinstance(error, sdk.APIError):
        return ModelAPIError(message, provider_name=provider_name)
    return None


__all__ = [
    "ModelAPIError",
    "ModelAuthenticationError",
    "ModelBadRequestError",
    "ModelConnectionError",
    "ModelError",
    "ModelRateLimitError",
    "ModelTimeoutError",
    "map_provider_error",
]
