"""
Utility functions and classes for the Mindtrace core package.

This module provides common utilities for downloading files, logging,
system checks, and other shared functionality across Mindtrace components.
"""

# Download utilities
from .downloads import (
    download_file,
    extract_zip,
    extract_tarball,
    download_and_extract_zip,
    download_and_extract_tarball,
    get_file_size,
    verify_download,
    DownloadProgressBar
)
# System checks (if available)
try:
    from .checks import *
except ImportError:
    pass

__all__ = [
    # Download utilities
    'download_file',
    'extract_zip', 
    'extract_tarball',
    'download_and_extract_zip',
    'download_and_extract_tarball',
    'get_file_size',
    'verify_download',
    'DownloadProgressBar',
]
