"""PathArchiver for preserving file/directory names when saving to Registry."""

import json
import shutil
import tarfile
import tempfile
from pathlib import Path, PosixPath, PurePath, WindowsPath
from typing import Any, ClassVar, Tuple, Type

from zenml.enums import ArtifactType

from mindtrace.registry.core.archiver import Archiver


class PathArchiver(Archiver):
    """Archiver for Path objects that preserves original filenames.

    Unlike ZenML's PathMaterializer which saves files with a generic name,
    this archiver preserves the original filename (including extension)
    when saving and loading Path objects.
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (Path, PosixPath, WindowsPath, PurePath)
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA
    METADATA_FILE: ClassVar[str] = "metadata.json"
    ARCHIVE_NAME: ClassVar[str] = "data.tar.gz"

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, data: Path) -> None:
        """Save a Path object (file or directory) to the artifact store.

        Args:
            data: Path to a local file or directory to store.

        Raises:
            TypeError: If data is not a Path object.
            FileNotFoundError: If the path does not exist.
        """
        if not isinstance(data, (Path, PosixPath, WindowsPath, PurePath)):
            raise TypeError(f"Expected a Path object, got {type(data).__name__}")

        # Convert to Path if needed
        data = Path(data)

        if not data.exists():
            raise FileNotFoundError(f"Path does not exist: {data}")

        uri_path = Path(self.uri)
        uri_path.mkdir(parents=True, exist_ok=True)

        # Store metadata with original name and type
        metadata = {
            "name": data.name,
            "is_dir": data.is_dir(),
        }

        with open(uri_path / self.METADATA_FILE, "w") as f:
            json.dump(metadata, f)

        if data.is_dir():
            # Create tar.gz archive for directories
            archive_base = uri_path / "data"
            shutil.make_archive(
                base_name=str(archive_base),
                format="gztar",
                root_dir=str(data),
            )
        else:
            # Copy file with original name
            shutil.copy2(str(data), str(uri_path / data.name))

    def load(self, data_type: Type[Any]) -> Path:
        """Load a Path object from the artifact store.

        Args:
            data_type: The type to load (unused, always returns Path).

        Returns:
            Path to the restored file or directory with original name.

        Raises:
            FileNotFoundError: If the artifact metadata is not found.
        """
        uri_path = Path(self.uri)
        metadata_path = uri_path / self.METADATA_FILE

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found at {metadata_path}")

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        original_name = metadata["name"]
        is_dir = metadata["is_dir"]

        # Create a temporary directory that persists after this method returns
        temp_dir = tempfile.mkdtemp()

        if is_dir:
            # Extract archive to temp directory with original name
            archive_path = uri_path / self.ARCHIVE_NAME
            if not archive_path.exists():
                raise FileNotFoundError(f"Archive not found at {archive_path}")

            # Create directory with original name
            output_dir = Path(temp_dir) / original_name
            output_dir.mkdir(parents=True, exist_ok=True)

            with tarfile.open(str(archive_path), "r:gz") as tar:
                tar.extractall(path=str(output_dir))

            return output_dir
        else:
            # Copy file to temp directory with original name
            source_file = uri_path / original_name
            if not source_file.exists():
                raise FileNotFoundError(f"File not found at {source_file}")

            dest_file = Path(temp_dir) / original_name
            shutil.copy2(str(source_file), str(dest_file))

            return dest_file
