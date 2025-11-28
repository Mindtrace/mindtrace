"""Unit test methods for mindtrace.core.utils.hashing utility module."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mindtrace.core import compute_dir_hash


def test_compute_dir_hash_empty_directory():
    """Test computing hash of an empty directory."""
    with TemporaryDirectory() as temp_dir:
        hash_value = compute_dir_hash(temp_dir)
        
        # Hash should be deterministic (empty directory should always produce same hash)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 produces 64 hex characters
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_single_file():
    """Test computing hash of a directory with a single file."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_file = temp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        hash_value = compute_dir_hash(temp_dir)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_multiple_files():
    """Test computing hash of a directory with multiple files."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create multiple files
        (temp_path / "file1.txt").write_text("Content 1")
        (temp_path / "file2.txt").write_text("Content 2")
        (temp_path / "file3.txt").write_text("Content 3")
        
        hash_value = compute_dir_hash(temp_dir)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_nested_directories():
    """Test computing hash of a directory with nested subdirectories."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create nested structure
        (temp_path / "file1.txt").write_text("Root file")
        (temp_path / "subdir1").mkdir()
        (temp_path / "subdir1" / "file2.txt").write_text("Subdir file")
        (temp_path / "subdir1" / "subdir2").mkdir()
        (temp_path / "subdir1" / "subdir2" / "file3.txt").write_text("Nested file")
        
        hash_value = compute_dir_hash(temp_dir)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_deterministic():
    """Test that the same directory structure produces the same hash."""
    with TemporaryDirectory() as temp_dir1, TemporaryDirectory() as temp_dir2:
        temp_path1 = Path(temp_dir1)
        temp_path2 = Path(temp_dir2)
        
        # Create identical structures in both directories
        (temp_path1 / "file1.txt").write_text("Content")
        (temp_path1 / "subdir").mkdir()
        (temp_path1 / "subdir" / "file2.txt").write_text("Nested content")
        
        (temp_path2 / "file1.txt").write_text("Content")
        (temp_path2 / "subdir").mkdir()
        (temp_path2 / "subdir" / "file2.txt").write_text("Nested content")
        
        hash1 = compute_dir_hash(temp_dir1)
        hash2 = compute_dir_hash(temp_dir2)
        
        # Same structure should produce same hash
        assert hash1 == hash2


def test_compute_dir_hash_different_content():
    """Test that different file contents produce different hashes."""
    with TemporaryDirectory() as temp_dir1, TemporaryDirectory() as temp_dir2:
        temp_path1 = Path(temp_dir1)
        temp_path2 = Path(temp_dir2)
        
        # Create directories with same structure but different content
        (temp_path1 / "file.txt").write_text("Content 1")
        (temp_path2 / "file.txt").write_text("Content 2")
        
        hash1 = compute_dir_hash(temp_dir1)
        hash2 = compute_dir_hash(temp_dir2)
        
        # Different content should produce different hashes
        assert hash1 != hash2


def test_compute_dir_hash_different_structure():
    """Test that different directory structures produce different hashes."""
    with TemporaryDirectory() as temp_dir1, TemporaryDirectory() as temp_dir2:
        temp_path1 = Path(temp_dir1)
        temp_path2 = Path(temp_dir2)
        
        # Create directories with different structures
        (temp_path1 / "file1.txt").write_text("Content")
        (temp_path1 / "file2.txt").write_text("Content")
        
        (temp_path2 / "file1.txt").write_text("Content")
        (temp_path2 / "subdir").mkdir()
        (temp_path2 / "subdir" / "file2.txt").write_text("Content")
        
        hash1 = compute_dir_hash(temp_dir1)
        hash2 = compute_dir_hash(temp_dir2)
        
        # Different structure should produce different hashes
        assert hash1 != hash2


def test_compute_dir_hash_file_order_independent():
    """Test that file order doesn't matter (files are sorted)."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create files in one order
        (temp_path / "z_file.txt").write_text("Z content")
        (temp_path / "a_file.txt").write_text("A content")
        (temp_path / "m_file.txt").write_text("M content")
        
        hash1 = compute_dir_hash(temp_dir)
        
        # Delete and recreate in different order
        for f in temp_path.glob("*.txt"):
            f.unlink()
        
        (temp_path / "a_file.txt").write_text("A content")
        (temp_path / "m_file.txt").write_text("M content")
        (temp_path / "z_file.txt").write_text("Z content")
        
        hash2 = compute_dir_hash(temp_dir)
        
        # Should produce same hash regardless of creation order
        assert hash1 == hash2


def test_compute_dir_hash_ignores_directories():
    """Test that directories themselves are not hashed, only files."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create directory structure
        (temp_path / "file.txt").write_text("Content")
        (temp_path / "empty_dir").mkdir()
        
        hash_with_empty_dir = compute_dir_hash(temp_dir)
        
        # Remove empty directory
        (temp_path / "empty_dir").rmdir()
        
        hash_without_dir = compute_dir_hash(temp_dir)
        
        # Hash should be the same (empty directories don't affect hash)
        assert hash_with_empty_dir == hash_without_dir


def test_compute_dir_hash_accepts_path_object():
    """Test that compute_dir_hash accepts Path objects."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "file.txt").write_text("Content")
        
        # Test with Path object
        hash_path = compute_dir_hash(temp_path)
        
        # Test with string
        hash_str = compute_dir_hash(temp_dir)
        
        # Should produce same hash
        assert hash_path == hash_str
        assert isinstance(hash_path, str)
        assert len(hash_path) == 64


def test_compute_dir_hash_accepts_string():
    """Test that compute_dir_hash accepts string paths."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "file.txt").write_text("Content")
        
        # Test with string
        hash_str = compute_dir_hash(temp_dir)
        
        # Test with Path object
        hash_path = compute_dir_hash(temp_path)
        
        # Should produce same hash
        assert hash_str == hash_path
        assert isinstance(hash_str, str)
        assert len(hash_str) == 64


def test_compute_dir_hash_binary_files():
    """Test computing hash with binary file content."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create binary file
        binary_content = bytes([0x00, 0x01, 0x02, 0xFF, 0xFE, 0xFD])
        (temp_path / "binary.bin").write_bytes(binary_content)
        
        hash_value = compute_dir_hash(temp_dir)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_large_file():
    """Test computing hash with a larger file."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create a larger file (1MB)
        large_content = "A" * (1024 * 1024)
        (temp_path / "large.txt").write_text(large_content)
        
        hash_value = compute_dir_hash(temp_dir)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2


def test_compute_dir_hash_special_characters_in_path():
    """Test computing hash with special characters in file paths."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create files with special characters in names
        (temp_path / "file with spaces.txt").write_text("Content")
        (temp_path / "file-with-dashes.txt").write_text("Content")
        (temp_path / "file_with_underscores.txt").write_text("Content")
        (temp_path / "file.with.dots.txt").write_text("Content")
        
        hash_value = compute_dir_hash(temp_dir)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        
        # Compute again to verify determinism
        hash_value2 = compute_dir_hash(temp_dir)
        assert hash_value == hash_value2

