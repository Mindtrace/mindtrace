import io
import logging
from tempfile import TemporaryDirectory

from mindtrace.registry import Registry


def test_registry_debug_logs_do_not_propagate_to_root_logger():
    """Registry debug logs should not leak to root handlers.

    This reproduces the noisy-console scenario where another dependency
    (e.g. ZenML) configures root handlers. Registry backend debug logs should
    remain internal unless explicitly opted in.
    """
    root_logger = logging.getLogger()
    old_level = root_logger.level

    capture_stream = io.StringIO()
    capture_handler = logging.StreamHandler(capture_stream)
    capture_handler.setLevel(logging.DEBUG)

    root_logger.addHandler(capture_handler)
    root_logger.setLevel(logging.DEBUG)

    try:
        with TemporaryDirectory() as temp_dir:
            registry = Registry(backend=temp_dir, version_objects=True)
            registry.save("a:shareditem", 1)
            assert registry.load("a:shareditem") == 1

        output = capture_stream.getvalue()
        assert "Loading metadata from:" not in output
        assert "Loaded metadata:" not in output
        assert "Downloading directory from" not in output
        assert "Download complete." not in output
    finally:
        root_logger.removeHandler(capture_handler)
        root_logger.setLevel(old_level)
