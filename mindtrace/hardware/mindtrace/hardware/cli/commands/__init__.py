"""CLI command modules."""

from mindtrace.hardware.cli.commands.camera import camera
from mindtrace.hardware.cli.commands.status import status_command

__all__ = ["camera", "status_command"]
