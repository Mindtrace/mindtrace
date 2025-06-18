"""
Mindtrace Core Package

This package provides the core functionality for the Mindtrace project,
including base classes, utilities, and common functionality shared across
all Mindtrace components.
"""

# Base classes and core functionality
from mindtrace.core.utils.checks import ifnone, first_not_none
from mindtrace.core.base.mindtrace_base import Mindtrace, MindtraceABC

# Configuration
from mindtrace.core.config import Config, get_config

# Download utilities
from mindtrace.core.utils.downloads import (
    download_file,
    extract_zip,
    extract_tarball,
    download_and_extract_zip,
    download_and_extract_tarball,
    get_file_size,
    verify_download,
    DownloadProgressBar
)


__all__ = [
    # Core functionality
    "first_not_none", 
    "ifnone", 
    "Mindtrace", 
    "MindtraceABC",
    
    # Configuration
    "Config",
    "get_config",
    
    # Download utilities
    "download_file",
    "extract_zip",
    "extract_tarball", 
    "download_and_extract_zip",
    "download_and_extract_tarball",
    "get_file_size",
    "verify_download",
    "DownloadProgressBar",
]
