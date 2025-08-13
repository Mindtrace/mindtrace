import logging

import pytest
from _pytest.mark import Mark

empty_mark = Mark("", (), {})


def by_slow_marker(item):
    # Check if test is marked as slow
    is_slow = 0 if item.get_closest_marker("slow") is None else 1

    # Check if test is integration test
    is_integration = 1 if "integration" in str(item.fspath) else 0

    # Return tuple for sorting: (is_integration, is_slow)
    # This will sort unit tests first, then slow unit tests,
    # then integration tests, then slow integration tests
    return (is_integration, is_slow)


def pytest_addoption(parser):
    parser.addoption("--slow-last", action="store_true", default=False)


def pytest_collection_modifyitems(items, config):
    if config.getoption("--slow-last"):
        items.sort(key=by_slow_marker)


@pytest.fixture(autouse=True)
def configure_logging_for_tests(caplog):
    """Configure logging to work properly with caplog fixture.

    This fixture ensures that all Mindtrace loggers propagate their messages to the root logger so that caplog can
    capture them properly.
    """
    # Set caplog to capture all levels
    caplog.set_level(logging.DEBUG)

    # Configure the root logger to ensure proper propagation
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)

    # Ensure mindtrace loggers propagate to root
    mindtrace_logger = logging.getLogger("mindtrace")
    original_propagate = mindtrace_logger.propagate
    mindtrace_logger.propagate = True

    yield

    # Restore original settings
    root_logger.setLevel(original_level)
    mindtrace_logger.propagate = original_propagate


class MockAssets:
    """Class containing actual assets (e.g. images) for tests."""

    image_path = "tests/resources/hopper.png"
    mask_path = "tests/resources/hopper_mask.png"
    image_large_path = "tests/resources/hopper_large.png"
    image_small_path = "tests/resources/hopper_small.png"
    image_tiny_path = "tests/resources/hopper_tiny.png"
    image_square_path = "tests/resources/hopper_square.png"
    image_background_path = "tests/resources/office_in_a_small_city.png"

    @property
    def image(self):
        return Image.open(self.image_path).convert("RGB")

    @property
    def image_background_path(self):
        return "tests/resources/office_in_a_small_city.png"

    @property
    def prompt(self):
        return "An astronaut riding a horse"

    @property
    def image(self):
        if not hasattr(self, "_image"):
            from PIL import Image

            self._image = Image.open(self.image_path).convert("RGB")
        return self._image

    @property
    def image_mask(self):
        if not hasattr(self, "_image_mask"):
            from PIL import Image

            self._image_mask = Image.open(self.mask_path).convert("L")
        return self._image_mask

    @property
    def image_large(self):
        if not hasattr(self, "_image_large"):
            from PIL import Image

            self._image_large = Image.open(self.image_large_path).convert("RGB")
        return self._image_large

    @property
    def image_small(self):
        if not hasattr(self, "_image_small"):
            from PIL import Image

            self._image_small = Image.open(self.image_small_path).convert("RGB")
        return self._image_small

    @property
    def image_tiny(self):
        if not hasattr(self, "_image_tiny"):
            from PIL import Image

            self._image_tiny = Image.open(self.image_tiny_path).convert("RGB")
        return self._image_tiny

    @property
    def image_square(self):
        if not hasattr(self, "_image_square"):
            from PIL import Image

            self._image_square = Image.open(self.image_square_path).convert("RGB")
        return self._image_square

    @property
    def image_background(self):
        if not hasattr(self, "_image_background"):
            from PIL import Image

            self._image_background = Image.open(self.image_background_path).convert("RGB")
        return self._image_background

    @property
    def image_rgba(self):
        rgba = self.image.copy()
        rgba.putalpha(self.image_mask)
        assert rgba.mode == "RGBA"
        return rgba

    @property
    def image_la(self):
        la = self.image.copy().convert("LA")
        la.putalpha(self.image_mask)
        assert la.mode == "LA"
        return la

    @property
    def image_wide(self):
        return self.image.copy().transpose(self._get_pil().ROTATE_90)

    @property
    def image_tall(self):
        return self.image.copy()

    @property
    def image_ndarray_bgr(self):
        try:
            import cv2
        except ImportError:
            raise ImportError("cv2 is required for image_ndarray_bgr. Please install opencv-python.")
        image = cv2.imread(self.image_path)
        assert image.shape[-1] == 3  # assert BGR format
        return image

    @property
    def image_ndarray_bgra(self):
        try:
            import cv2
        except ImportError:
            raise ImportError("cv2 is required for image_ndarray_bgra. Please install opencv-python.")
        image = cv2.cvtColor(self.image_ndarray_bgr, cv2.COLOR_BGR2BGRA)
        mask = cv2.cvtColor(cv2.imread(self.mask_path), cv2.COLOR_BGR2GRAY)
        image[:, :, 3] = mask  # pylint: disable=unsupported-assignment-operation
        assert image.shape[-1] == 4  # assert BGRA format
        return image

    @property
    def image_uint8_ndarray(self):
        try:
            import numpy as np
        except ImportError:
            raise ImportError("numpy is required for image_uint8_ndarray. Please install numpy.")
        image_ndarray = np.asarray(self.image)
        assert image_ndarray.dtype == np.uint8
        return image_ndarray

    @property
    def image_float32_ndarray(self):
        try:
            import numpy as np
        except ImportError:
            raise ImportError("numpy is required for image_float32_ndarray. Please install numpy.")
        uint8_ndarray = self.image_uint8_ndarray
        fp32_ndarray = (uint8_ndarray / 255.0).astype(np.float32)
        assert fp32_ndarray.dtype == np.float32
        return fp32_ndarray

    def _get_pil(self):
        from PIL import Image

        return Image


@pytest.fixture(scope="session")
def mock_assets():
    """Fixture providing the MockAssets instance for all tests."""
    return MockAssets()
