"""CLI command modules."""

from mindtrace.hardware.cli.commands.camera import app as camera_app
from mindtrace.hardware.cli.commands.plc import app as plc_app
from mindtrace.hardware.cli.commands.status import status_command
from mindtrace.hardware.cli.commands.stereo import app as stereo_app

__all__ = ["camera_app", "plc_app", "stereo_app", "status_command"]
