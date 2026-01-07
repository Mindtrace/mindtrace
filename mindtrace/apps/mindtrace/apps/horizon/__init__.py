"""Horizon - Reference implementation app for mindtrace.

This module provides HorizonService, a demonstration service showcasing
the mindtrace ecosystem including:

- Configuration via HorizonConfig (extends mindtrace.core.Config)
- Image processing endpoints
- Async MongoDB integration
- Authentication middleware
- Proper resource management

Example:
    Launch the service:
    ```python
    from mindtrace.apps.horizon import HorizonService

    # Launch with blocking (for standalone execution)
    HorizonService.launch(block=True)

    # Launch non-blocking and get connection manager
    manager = HorizonService.launch()
    result = manager.echo({"message": "Hello!"})
    ```

    With config overrides:
    ```python
    from mindtrace.apps.horizon import HorizonConfig

    # With overrides
    HorizonService.launch(config_overrides=HorizonConfig(DEBUG=True), block=True)
    ```

    Via command line:
    ```bash
    uv run python -m mindtrace.apps.horizon

    # With environment overrides
    HORIZON__URL=http://0.0.0.0:9000 uv run python -m mindtrace.apps.horizon
    ```
"""

from . import image_ops
from .auth_middleware import AuthMiddleware
from .config import HorizonConfig, HorizonSettings
from .db import HorizonDB
from .horizon import HorizonService
from .jobs import ImageProcessingJobStore
from .types import ImageProcessingJob

__all__ = [
    "AuthMiddleware",
    "HorizonConfig",
    "HorizonDB",
    "HorizonService",
    "HorizonSettings",
    "ImageProcessingJob",
    "ImageProcessingJobStore",
    "image_ops",
]
