"""Utility methods for unit tests."""

import uuid
from pathlib import Path

import PIL
from PIL.Image import Image

from mindtrace.core.config import CoreConfig


def images_are_identical(image_1: Image, image_2: Image):
    if image_1.mode != image_2.mode:
        return False
    elif image_1.mode in ["1", "L"]:
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == ((0, 0))
    elif image_1.mode == "LA":
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == (
            (0, 0),
            (0, 0),
        )
    elif image_1.mode == "RGB":
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == (
            (0, 0),
            (0, 0),
            (0, 0),
        )
    elif image_1.mode == "RGBA":
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == (
            (0, 0),
            (0, 0),
            (0, 0),
            (0, 0),
        )
    else:
        raise NotImplementedError(f"Unable to compare images of type {image_1.mode}.")


def create_large_file_or_directory(
    target_path: str | Path | None = None, size_mb: float = 1024.0, as_directory: bool = False, num_files: int = 10
) -> Path:
    """Create a large file or directory for testing large data with Registry.

    This function is meant as a utility to create large files or directories for testing.

    Args:
        target_path: Path where to create the file or directory. If None, creates a file/directory
            in the mindtrace temp directory (from CoreConfig TEMP_DIR) with a UUID-based name (default: None)
        size_mb: Target size in MB (default: 1GB)
        as_directory: If True, creates a directory with multiple files. If False, creates a single file.
        num_files: Number of files to create if as_directory=True (default: 10)

    Returns:
        Path to the created file or directory

    Example::
        from tests.utils.utils import create_large_file_or_directory
        from pathlib import Path

        # Create a single 1GB file (1024 MB) with auto-generated UUID path
        large_file = create_large_file_or_directory(size_mb=1024.0)

        # Create a directory with 10 files totaling ~1GB with auto-generated UUID path
        large_dir = create_large_file_or_directory(size_mb=1024.0, as_directory=True, num_files=10)

        # Create a smaller 100MB file with custom path
        small_file = create_large_file_or_directory("/tmp/small_data.bin", size_mb=100.0)
    """
    if target_path is None:
        # Generate default path with UUID in mindtrace temp directory
        config = CoreConfig()
        temp_dir = Path(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        unique_id = uuid.uuid4().hex
        if as_directory:
            target_path = temp_dir / f"registry_test_{unique_id}"
        else:
            target_path = temp_dir / f"registry_test_{unique_id}.bin"
    
    target_path = Path(target_path)
    size_bytes = int(size_mb * 1024 * 1024)  # Convert MB to bytes

    if as_directory:
        # Create directory with multiple files
        target_path.mkdir(parents=True, exist_ok=True)
        file_size = size_bytes // num_files

        # Create a pattern of bytes to write (repeated pattern for efficiency)
        pattern = b"X" * min(1024 * 1024, file_size)  # 1MB chunks or smaller

        for i in range(num_files):
            file_path = target_path / f"file_{i:04d}.bin"
            with open(file_path, "wb") as f:
                remaining = file_size
                while remaining > 0:
                    write_size = min(len(pattern), remaining)
                    f.write(pattern[:write_size])
                    remaining -= write_size
    else:
        # Create a single large file
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Create a pattern of bytes to write (1MB chunks for efficiency)
        pattern = b"X" * (1024 * 1024)  # 1MB pattern

        with open(target_path, "wb") as f:
            remaining = size_bytes
            while remaining > 0:
                write_size = min(len(pattern), remaining)
                f.write(pattern[:write_size])
                remaining -= write_size

    return target_path
