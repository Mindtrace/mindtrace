"""Image loading utilities with parallel I/O support.

Provides a thread-safe image loader that reads images from local paths using
concurrent execution for improved throughput.
"""

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

try:
    import numpy as np

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - environment dependent
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

try:
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover - environment dependent
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

from mindtrace.core.base import Mindtrace


class ImageLoader(Mindtrace):
    """Thread-safe parallel image loader with configurable color mode.

    Extends Mindtrace for structured logging of I/O errors during parallel loading.
    Images are read using OpenCV and optionally converted to RGB color space.

    Usage:
        ```python
        from mindtrace.core import ImageLoader

        loader = ImageLoader(num_workers=4, color_mode="rgb")

        # Load named images
        images = loader.load({
            "front": "/path/to/front.jpg",
            "back": "/path/to/back.jpg",
        })

        # Load a batch of images
        batch = loader.load_batch(["/path/to/img1.jpg", "/path/to/img2.jpg"])
        ```
    """

    def __init__(
        self,
        num_workers: int = 4,
        color_mode: Literal["rgb", "bgr"] = "rgb",
        **kwargs,
    ) -> None:
        """Initialize the ImageLoader.

        Args:
            num_workers: Maximum number of threads for parallel I/O.
            color_mode: Color space for loaded images. "rgb" converts BGR to RGB,
                        "bgr" keeps the native OpenCV format.
            **kwargs: Additional keyword arguments passed to Mindtrace.
        """
        super().__init__(**kwargs)

        if not _HAS_NUMPY:
            raise ImportError("numpy is required for ImageLoader but is not installed.")
        if not _HAS_CV2:
            raise ImportError("cv2 (opencv-python) is required for ImageLoader but is not installed.")

        if num_workers < 1:
            raise ValueError(f"num_workers must be >= 1, got {num_workers}")
        if color_mode not in ("rgb", "bgr"):
            raise ValueError(f"color_mode must be 'rgb' or 'bgr', got {color_mode!r}")

        self.num_workers = num_workers
        self.color_mode = color_mode

    def _read_single(self, key: str, path: str) -> tuple[str, "np.ndarray"]:
        """Read a single image from disk.

        Args:
            key: Identifier for the image.
            path: Absolute path to the image file.

        Returns:
            Tuple of (key, image_array).

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the image could not be decoded.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {path} (key: {key})")

        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Could not decode image: {path} (key: {key})")

        if self.color_mode == "rgb":
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        return key, img

    def load(self, paths: dict[str, str]) -> dict[str, "np.ndarray"]:
        """Load named images from local paths in parallel.

        Args:
            paths: Mapping of {name: absolute_path} for each image.

        Returns:
            Mapping of {name: numpy_array} preserving input order.
            Images that fail to load are excluded (errors are logged).
        """
        if not paths:
            return {}

        results: dict[str, "np.ndarray"] = {}
        keys_order = list(paths.keys())

        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            future_to_key: dict[Future, str] = {
                executor.submit(self._read_single, key, path): key
                for key, path in paths.items()
            }

            for future in as_completed(future_to_key):
                submitted_key = future_to_key[future]
                try:
                    key, img = future.result()
                    results[key] = img
                except Exception:
                    self.logger.exception(
                        "Failed to load image for key '%s' at path '%s'",
                        submitted_key,
                        paths[submitted_key],
                    )

        # Return in input order
        return {k: results[k] for k in keys_order if k in results}

    def load_batch(self, paths: list[str]) -> list["np.ndarray"]:
        """Load a list of images from local paths in parallel.

        Args:
            paths: List of absolute paths to image files.

        Returns:
            List of numpy arrays in the same order as input paths.
            Failed images are replaced with None entries and logged.
        """
        if not paths:
            return []

        indexed_results: dict[int, "np.ndarray | None"] = {}

        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            future_to_idx: dict[Future, int] = {
                executor.submit(self._read_single, str(idx), path): idx
                for idx, path in enumerate(paths)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    _, img = future.result()
                    indexed_results[idx] = img
                except Exception:
                    self.logger.exception(
                        "Failed to load image at index %d, path '%s'",
                        idx,
                        paths[idx],
                    )
                    indexed_results[idx] = None

        # Reconstruct in original order, filtering out failures
        output: list["np.ndarray"] = []
        for idx in range(len(paths)):
            img = indexed_results.get(idx)
            if img is not None:
                output.append(img)
            else:
                self.logger.warning(
                    "Image at index %d excluded from batch result (load failed)", idx
                )

        return output

    def __repr__(self) -> str:
        return (
            f"ImageLoader(num_workers={self.num_workers}, "
            f"color_mode={self.color_mode!r})"
        )
