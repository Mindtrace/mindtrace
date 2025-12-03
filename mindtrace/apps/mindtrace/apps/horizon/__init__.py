"""Horizon - Reference implementation app for mindtrace.

This module provides HorizonService, a demonstration service showcasing
the mindtrace ecosystem including:

- Configuration via mindtrace.core.Config
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

    Via command line:
    ```bash
    uv run python -m mindtrace.apps.horizon
    ```
"""

from .auth_middleware import AuthMiddleware
from .config import HorizonSettings, get_horizon_config
from .db import HorizonDB
from .horizon import HorizonService
from .jobs import ImageProcessingJobStore
from .types import ImageProcessingJob
from . import image_ops

__all__ = [
    "AuthMiddleware",
    "HorizonDB",
    "HorizonService",
    "HorizonSettings",
    "ImageProcessingJob",
    "ImageProcessingJobStore",
    "get_horizon_config",
    "image_ops",
]

