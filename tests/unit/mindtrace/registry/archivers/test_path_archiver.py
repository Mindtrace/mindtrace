"""Unit tests for PathArchiver."""

import tempfile
from pathlib import Path, PosixPath

import pytest

from mindtrace.registry.archivers.path_archiver import PathArchiver


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def path_archiver(temp_dir):
    """Create a PathArchiver instance."""
    return PathArchiver(uri=temp_dir)


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample file for testing."""
    file_path = Path(temp_dir) / "input" / "sample_file.txt"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("Hello, World!")
    return file_path


@pytest.fixture
def sample_json_file(temp_dir):
    """Create a sample JSON file for testing."""
    file_path = Path(temp_dir) / "input" / "config.json"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text('{"key": "value"}')
    return file_path


@pytest.fixture
def sample_dir(temp_dir):
    """Create a sample directory with files for testing."""
    dir_path = Path(temp_dir) / "input" / "sample_directory"
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "file1.txt").write_text("File 1 content")
    (dir_path / "file2.txt").write_text("File 2 content")
    subdir = dir_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("File 3 content")
    return dir_path


class TestPathArchiverInit:
    def test_path_archiver_init(self, path_archiver, temp_dir):
        """Test PathArchiver initialization."""
        assert path_archiver.uri == temp_dir
        assert hasattr(path_archiver, "logger")

    def test_path_archiver_class_attributes(self):
        """Test PathArchiver class attributes."""
        assert PathArchiver.METADATA_FILE == "metadata.json"
        assert PathArchiver.ARCHIVE_NAME == "data.tar.gz"
        assert Path in PathArchiver.ASSOCIATED_TYPES
        assert PosixPath in PathArchiver.ASSOCIATED_TYPES


class TestPathArchiverSaveFile:
    def test_save_file_creates_metadata(self, temp_dir, sample_file):
        """Test that save creates metadata.json with correct content."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_file)

        metadata_path = archiver_uri / "metadata.json"
        assert metadata_path.exists()

        import json

        with open(metadata_path) as f:
            metadata = json.load(f)

        assert metadata["name"] == "sample_file.txt"
        assert metadata["is_dir"] is False

    def test_save_file_copies_with_original_name(self, temp_dir, sample_file):
        """Test that save copies file with original name."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_file)

        saved_file = archiver_uri / "sample_file.txt"
        assert saved_file.exists()
        assert saved_file.read_text() == "Hello, World!"

    def test_save_file_with_json_extension(self, temp_dir, sample_json_file):
        """Test that save preserves .json extension."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_json_file)

        saved_file = archiver_uri / "config.json"
        assert saved_file.exists()
        assert "key" in saved_file.read_text()

    def test_save_raises_type_error_for_non_path(self, path_archiver):
        """Test that save raises TypeError for non-Path objects."""
        with pytest.raises(TypeError, match="Expected a Path object"):
            path_archiver.save("not a path")

    def test_save_raises_file_not_found_for_missing_path(self, path_archiver, temp_dir):
        """Test that save raises FileNotFoundError for non-existent paths."""
        missing_path = Path(temp_dir) / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            path_archiver.save(missing_path)


class TestPathArchiverSaveDirectory:
    def test_save_directory_creates_metadata(self, temp_dir, sample_dir):
        """Test that save creates metadata.json for directories."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_dir)

        metadata_path = archiver_uri / "metadata.json"
        assert metadata_path.exists()

        import json

        with open(metadata_path) as f:
            metadata = json.load(f)

        assert metadata["name"] == "sample_directory"
        assert metadata["is_dir"] is True

    def test_save_directory_creates_archive(self, temp_dir, sample_dir):
        """Test that save creates tar.gz archive for directories."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_dir)

        archive_path = archiver_uri / "data.tar.gz"
        assert archive_path.exists()


class TestPathArchiverLoadFile:
    def test_load_file_preserves_filename(self, temp_dir, sample_file):
        """Test that load returns Path with original filename."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_file)
        loaded_path = archiver.load(Path)

        assert loaded_path.name == "sample_file.txt"
        assert loaded_path.suffix == ".txt"
        assert loaded_path.exists()

    def test_load_file_preserves_content(self, temp_dir, sample_file):
        """Test that load returns file with original content."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_file)
        loaded_path = archiver.load(Path)

        assert loaded_path.read_text() == "Hello, World!"

    def test_load_file_preserves_json_extension(self, temp_dir, sample_json_file):
        """Test that load preserves .json extension."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_json_file)
        loaded_path = archiver.load(Path)

        assert loaded_path.name == "config.json"
        assert loaded_path.suffix == ".json"

    def test_load_raises_file_not_found_for_missing_metadata(self, temp_dir):
        """Test that load raises FileNotFoundError for missing metadata."""
        archiver = PathArchiver(uri=temp_dir)

        with pytest.raises(FileNotFoundError, match="Metadata not found"):
            archiver.load(Path)

    def test_load_raises_file_not_found_for_missing_file(self, temp_dir):
        """Test that load raises FileNotFoundError when file data is missing."""
        import json

        archiver_uri = Path(temp_dir) / "archiver"
        archiver_uri.mkdir(parents=True)
        archiver = PathArchiver(uri=str(archiver_uri))

        # Create metadata indicating a file, but don't create the actual file
        metadata = {"name": "missing_file.txt", "is_dir": False}
        with open(archiver_uri / "metadata.json", "w") as f:
            json.dump(metadata, f)

        with pytest.raises(FileNotFoundError, match="File not found"):
            archiver.load(Path)


class TestPathArchiverLoadDirectory:
    def test_load_directory_preserves_name(self, temp_dir, sample_dir):
        """Test that load returns directory with original name."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_dir)
        loaded_path = archiver.load(Path)

        assert loaded_path.name == "sample_directory"
        assert loaded_path.is_dir()

    def test_load_directory_preserves_contents(self, temp_dir, sample_dir):
        """Test that load returns directory with all original files."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        archiver.save(sample_dir)
        loaded_path = archiver.load(Path)

        assert (loaded_path / "file1.txt").exists()
        assert (loaded_path / "file1.txt").read_text() == "File 1 content"
        assert (loaded_path / "file2.txt").exists()
        assert (loaded_path / "subdir" / "file3.txt").exists()

    def test_load_raises_file_not_found_for_missing_archive(self, temp_dir):
        """Test that load raises FileNotFoundError when archive is missing."""
        import json

        archiver_uri = Path(temp_dir) / "archiver"
        archiver_uri.mkdir(parents=True)
        archiver = PathArchiver(uri=str(archiver_uri))

        # Create metadata indicating a directory, but don't create the archive
        metadata = {"name": "missing_directory", "is_dir": True}
        with open(archiver_uri / "metadata.json", "w") as f:
            json.dump(metadata, f)

        with pytest.raises(FileNotFoundError, match="Archive not found"):
            archiver.load(Path)


class TestPathArchiverRoundTrip:
    def test_round_trip_file_with_various_extensions(self, temp_dir):
        """Test save/load round trip for files with various extensions."""
        extensions = [".txt", ".json", ".pt", ".csv", ".yaml", ".py"]

        for ext in extensions:
            archiver_uri = Path(temp_dir) / f"archiver_{ext[1:]}"
            archiver = PathArchiver(uri=str(archiver_uri))

            input_dir = Path(temp_dir) / "input"
            input_dir.mkdir(exist_ok=True)
            input_file = input_dir / f"test_file{ext}"
            input_file.write_text(f"Content for {ext}")

            archiver.save(input_file)
            loaded_path = archiver.load(Path)

            assert loaded_path.name == f"test_file{ext}"
            assert loaded_path.suffix == ext
            assert loaded_path.read_text() == f"Content for {ext}"

    def test_round_trip_empty_file(self, temp_dir):
        """Test save/load round trip for empty files."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        input_dir = Path(temp_dir) / "input"
        input_dir.mkdir(exist_ok=True)
        input_file = input_dir / "empty.txt"
        input_file.touch()

        archiver.save(input_file)
        loaded_path = archiver.load(Path)

        assert loaded_path.name == "empty.txt"
        assert loaded_path.read_text() == ""

    def test_round_trip_file_without_extension(self, temp_dir):
        """Test save/load round trip for files without extension."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        input_dir = Path(temp_dir) / "input"
        input_dir.mkdir(exist_ok=True)
        input_file = input_dir / "Makefile"
        input_file.write_text("all:\n\techo hello")

        archiver.save(input_file)
        loaded_path = archiver.load(Path)

        assert loaded_path.name == "Makefile"
        assert loaded_path.suffix == ""

    def test_round_trip_empty_directory(self, temp_dir):
        """Test save/load round trip for empty directories."""
        archiver_uri = Path(temp_dir) / "archiver"
        archiver = PathArchiver(uri=str(archiver_uri))

        input_dir = Path(temp_dir) / "input" / "empty_dir"
        input_dir.mkdir(parents=True)

        archiver.save(input_dir)
        loaded_path = archiver.load(Path)

        assert loaded_path.name == "empty_dir"
        assert loaded_path.is_dir()
        assert list(loaded_path.iterdir()) == []
