import logging
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Union
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)


def download_and_extract_zip(
    url: str, extract_to: Union[str, Path], filename: Optional[str] = None, remove_after_extract: bool = True
) -> Path:
    """
    Download a ZIP file from URL and extract it to the specified directory.

    Args:
        url: URL to download the ZIP file from
        extract_to: Directory to extract the ZIP file to
        filename: Optional filename for the downloaded file (if None, uses URL basename)
        remove_after_extract: Whether to remove the downloaded ZIP file after extraction

    Returns:
        Path to the extracted directory

    Raises:
        Exception: If download or extraction fails
    """
    extract_to = Path(extract_to).expanduser()
    extract_to.mkdir(parents=True, exist_ok=True)

    # Create temporary directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Determine filename
        if filename is None:
            filename = url.split("/")[-1]
            if not filename.endswith(".zip"):
                filename += ".zip"

        zip_path = temp_path / filename

        try:
            logger.info(f"Downloading ZIP from {url} to {zip_path}")
            urlretrieve(url, zip_path)

            logger.info(f"Extracting ZIP to {extract_to}")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_to)

            logger.info(f"Successfully extracted ZIP to {extract_to}")
            return extract_to

        except Exception as e:
            logger.error(f"Failed to download or extract ZIP: {e}")
            # Clean up any partial files
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except Exception:
                    pass
            raise


def download_and_extract_tarball(
    url: str, extract_to: Union[str, Path], filename: Optional[str] = None, remove_after_extract: bool = True
) -> Path:
    """
    Download a tarball (tar.gz, tar.bz2, etc.) from URL and extract it to the specified directory.

    Args:
        url: URL to download the tarball from
        extract_to: Directory to extract the tarball to
        filename: Optional filename for the downloaded file (if None, uses URL basename)
        remove_after_extract: Whether to remove the downloaded tarball after extraction

    Returns:
        Path to the extracted directory

    Raises:
        Exception: If download or extraction fails
    """
    extract_to = Path(extract_to).expanduser()
    extract_to.mkdir(parents=True, exist_ok=True)

    # Create temporary directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Determine filename
        if filename is None:
            filename = url.split("/")[-1]

        tarball_path = temp_path / filename

        try:
            logger.info(f"Downloading tarball from {url} to {tarball_path}")
            urlretrieve(url, tarball_path)

            logger.info(f"Extracting tarball to {extract_to}")

            # Determine compression type and extract accordingly
            if filename.endswith(".tar.gz") or filename.endswith(".tgz"):
                mode = "r:gz"
            elif filename.endswith(".tar.bz2") or filename.endswith(".tbz2"):
                mode = "r:bz2"
            elif filename.endswith(".tar.xz") or filename.endswith(".txz"):
                mode = "r:xz"
            else:
                mode = "r"  # Assume uncompressed tar

            with tarfile.open(tarball_path, mode) as tar_ref:
                tar_ref.extractall(extract_to)

            logger.info(f"Successfully extracted tarball to {extract_to}")
            return extract_to

        except Exception as e:
            logger.error(f"Failed to download or extract tarball: {e}")
            # Clean up any partial files
            if tarball_path.exists():
                try:
                    tarball_path.unlink()
                except Exception:
                    pass
            raise
