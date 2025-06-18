"""
Download and extraction utilities for files and archives.

Provides functions for downloading files from URLs and extracting various archive formats
with progress bars and proper error handling.
"""

import os
import shutil
import tarfile
import zipfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse


class DownloadProgressBar:
    """Simple progress bar for downloads."""
    
    def __init__(self, total_size: int, description: str = "Downloading"):
        self.total_size = total_size
        self.downloaded = 0
        self.description = description
        self.last_percent = -1
    
    def update(self, chunk_size: int):
        """Update progress bar with downloaded chunk size."""
        self.downloaded += chunk_size
        if self.total_size > 0:
            percent = int((self.downloaded / self.total_size) * 100)
            if percent != self.last_percent and percent % 5 == 0:  # Update every 5%
                print(f"\r{self.description}: {percent}%", end="", flush=True)
                self.last_percent = percent
    
    def finish(self):
        """Complete the progress bar."""
        print(f"\r{self.description}: 100% - Complete!")


def download_file(url: str, destination: str, progress_bar: bool = True) -> str:
    """
    Download a file from URL to destination.
    
    Args:
        url: URL to download from
        destination: Local file path to save to
        progress_bar: Whether to show progress bar
        
    Returns:
        Path to downloaded file
        
    Raises:
        urllib.error.URLError: If download fails
        OSError: If file cannot be written
    """
    # Ensure destination directory exists
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    
    # Get file size for progress bar
    try:
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            filename = os.path.basename(destination)
            
            if progress_bar and total_size > 0:
                progress = DownloadProgressBar(total_size, f"Downloading {filename}")
            else:
                progress = None
                print(f"Downloading {filename}...")
            
            with open(destination, 'wb') as f:
                while True:
                    chunk = response.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    if progress:
                        progress.update(len(chunk))
            
            if progress:
                progress.finish()
            else:
                print(f"Downloaded {filename}")
                
    except Exception as e:
        # Clean up partial download
        if os.path.exists(destination):
            os.remove(destination)
        raise
    
    return destination


def extract_zip(zip_path: str, extract_to: str, remove_archive: bool = False) -> str:
    """
    Extract a ZIP archive.
    
    Args:
        zip_path: Path to ZIP file
        extract_to: Directory to extract to
        remove_archive: Whether to remove the archive after extraction
        
    Returns:
        Path to extracted directory
        
    Raises:
        zipfile.BadZipFile: If ZIP file is corrupted
        OSError: If extraction fails
    """
    os.makedirs(extract_to, exist_ok=True)
    
    print(f"Extracting {os.path.basename(zip_path)}...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Get the root directory name from the first entry
        names = zip_ref.namelist()
        if names:
            root_dir = names[0].split('/')[0]
        else:
            root_dir = os.path.splitext(os.path.basename(zip_path))[0]
        
        zip_ref.extractall(extract_to)
    
    extracted_path = os.path.join(extract_to, root_dir)
    
    if remove_archive:
        os.remove(zip_path)
        print(f"Removed archive {zip_path}")
    
    print(f"Extracted to {extracted_path}")
    return extracted_path


def extract_tarball(tar_path: str, extract_to: str, remove_archive: bool = False) -> str:
    """
    Extract a tarball (tar.gz, tar.bz2, etc.).
    
    Args:
        tar_path: Path to tarball file
        extract_to: Directory to extract to
        remove_archive: Whether to remove the archive after extraction
        
    Returns:
        Path to extracted directory
        
    Raises:
        tarfile.TarError: If tarball is corrupted
        OSError: If extraction fails
    """
    os.makedirs(extract_to, exist_ok=True)
    
    print(f"Extracting {os.path.basename(tar_path)}...")
    
    with tarfile.open(tar_path, 'r:*') as tar_ref:
        # Get the root directory name from the first entry
        names = tar_ref.getnames()
        if names:
            root_dir = names[0].split('/')[0]
        else:
            # Fallback to filename without extensions
            basename = os.path.basename(tar_path)
            root_dir = basename.replace('.tar.gz', '').replace('.tar.bz2', '').replace('.tar', '')
        
        tar_ref.extractall(extract_to)
    
    extracted_path = os.path.join(extract_to, root_dir)
    
    if remove_archive:
        os.remove(tar_path)
        print(f"Removed archive {tar_path}")
    
    print(f"Extracted to {extracted_path}")
    return extracted_path


def download_and_extract_zip(url: str, save_dir: str, progress_bar: bool = True, 
                           remove_archive: bool = True) -> str:
    """
    Download and extract a ZIP file in one operation.
    
    Args:
        url: URL to download ZIP from
        save_dir: Directory to save and extract to
        progress_bar: Whether to show download progress
        remove_archive: Whether to remove ZIP after extraction
        
    Returns:
        Path to extracted directory
        
    Raises:
        urllib.error.URLError: If download fails
        zipfile.BadZipFile: If ZIP file is corrupted
        OSError: If file operations fail
    """
    # Create save directory
    os.makedirs(save_dir, exist_ok=True)
    
    # Generate filename from URL
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    if not filename.endswith('.zip'):
        filename += '.zip'
    
    zip_path = os.path.join(save_dir, filename)
    
    try:
        # Download the file
        download_file(url, zip_path, progress_bar)
        
        # Extract the file
        extracted_path = extract_zip(zip_path, save_dir, remove_archive)
        
        return extracted_path
        
    except Exception as e:
        # Clean up on failure
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise


def download_and_extract_tarball(url: str, save_dir: str, progress_bar: bool = True,
                                remove_archive: bool = True) -> str:
    """
    Download and extract a tarball in one operation.
    
    Args:
        url: URL to download tarball from
        save_dir: Directory to save and extract to
        progress_bar: Whether to show download progress
        remove_archive: Whether to remove tarball after extraction
        
    Returns:
        Path to extracted directory
        
    Raises:
        urllib.error.URLError: If download fails
        tarfile.TarError: If tarball is corrupted
        OSError: If file operations fail
    """
    # Create save directory
    os.makedirs(save_dir, exist_ok=True)
    
    # Generate filename from URL
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    
    tar_path = os.path.join(save_dir, filename)
    
    try:
        # Download the file
        download_file(url, tar_path, progress_bar)
        
        # Extract the file
        extracted_path = extract_tarball(tar_path, save_dir, remove_archive)
        
        return extracted_path
        
    except Exception as e:
        # Clean up on failure
        if os.path.exists(tar_path):
            os.remove(tar_path)
        raise


def get_file_size(url: str) -> int:
    """
    Get the size of a file from URL without downloading it.
    
    Args:
        url: URL to check
        
    Returns:
        File size in bytes, or 0 if unknown
    """
    try:
        with urllib.request.urlopen(url) as response:
            return int(response.headers.get('Content-Length', 0))
    except:
        return 0


def verify_download(file_path: str, expected_size: Optional[int] = None) -> bool:
    """
    Verify a downloaded file exists and optionally check size.
    
    Args:
        file_path: Path to downloaded file
        expected_size: Expected file size in bytes (optional)
        
    Returns:
        True if file is valid, False otherwise
    """
    if not os.path.exists(file_path):
        return False
    
    if expected_size is not None:
        actual_size = os.path.getsize(file_path)
        return actual_size == expected_size
    
    return True 