import hashlib
from pathlib import Path


def compute_dir_hash(directory_path: str | Path) -> str:
    """Compute SHA256 hash of directory contents.

    Hash is deterministic: files are sorted by path, then each file's content is hashed and combined. This ensures the 
    same directory always produces the same hash.

    Args:
        directory_path: Path to the directory to hash

    Returns:
        Hexadecimal SHA256 hash string
    """
    directory_path = Path(directory_path)
    sha = hashlib.sha256()
    
    # Sort files for deterministic hashing
    # Only hash regular files, ignore directories
    files = sorted([f for f in directory_path.rglob("*") if f.is_file()])
    
    for file_path in files:
        # Include relative path in hash for uniqueness
        rel_path = file_path.relative_to(directory_path)
        sha.update(str(rel_path).encode('utf-8'))
        
        # Include file content
        sha.update(file_path.read_bytes())
    
    return sha.hexdigest()

