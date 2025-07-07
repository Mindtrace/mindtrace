#!/usr/bin/env python3
"""
Daheng Galaxy SDK Setup Script

This script automates the download and installation of the Daheng Galaxy SDK
for both Linux and Windows systems. The Galaxy SDK is required to connect
and use Daheng cameras in the Mindtrace hardware system.

Features:
- Automatic SDK download from GitHub releases
- Platform-specific installation (Linux .run script, Windows .exe)
- Administrative privilege handling for Windows
- Comprehensive logging and error handling
- Uninstallation support
- gxipy library integration

Usage:
    python setup_daheng.py                    # Install SDK
    python setup_daheng.py --uninstall        # Uninstall SDK
    mindtrace-setup-daheng                     # Console script (install)
    mindtrace-uninstall-daheng                 # Console script (uninstall)

Note:
    The Windows SDK installer automatically includes the gxipy Python library.
    For Linux, the gxipy library may need to be installed separately after SDK installation.
"""

import argparse
import ctypes
import logging
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

from mindtrace.core.base.mindtrace_base import Mindtrace
from mindtrace.core.utils import download_and_extract_zip, download_and_extract_tarball
from mindtrace.hardware.mindtrace.hardware.core.config import get_hardware_config


class DahengSDKInstaller(Mindtrace):
    """
    Daheng Galaxy SDK installer and manager.
    
    This class handles the download, installation, and uninstallation
    of the Daheng Galaxy SDK across different platforms.
    """
    
    # SDK URLs for different platforms
    LINUX_SDK_URL_TEMPLATE = "https://github.com/Mindtrace/gxipy/releases/download/{version}/Galaxy_Linux.tar.gz"
    WINDOWS_SDK_URL_TEMPLATE = "https://github.com/Mindtrace/gxipy/releases/download/{version}/Galaxy_Windows.zip"
    
    def __init__(self, release_version: str = "v1.0-stable"):
        """
        Initialize the Daheng SDK installer.
        
        Args:
            release_version: SDK release version to download
        """
        # Initialize base class first
        super().__init__()
        
        # Get hardware configuration
        self.hardware_config = get_hardware_config()
        
        self.release_version = release_version
        self.daheng_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "daheng"
        self.platform = platform.system()
        
        # Generate URLs based on version
        self.linux_sdk_url = self.LINUX_SDK_URL_TEMPLATE.format(version=release_version)
        self.windows_sdk_url = self.WINDOWS_SDK_URL_TEMPLATE.format(version=release_version)
        
        self.logger.info(f"Initializing Daheng SDK installer for {self.platform}")
        self.logger.debug(f"Release version: {release_version}")
        self.logger.debug(f"Installation directory: {self.daheng_dir}")
        self.logger.debug(f"Linux SDK URL: {self.linux_sdk_url}")
        self.logger.debug(f"Windows SDK URL: {self.windows_sdk_url}")
    
    def install(self) -> bool:
        """
        Install the Daheng SDK for the current platform.
        
        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Starting Daheng Galaxy SDK installation")
        
        try:
            if self.platform == "Linux":
                return self._install_linux()
            elif self.platform == "Windows":
                return self._install_windows()
            else:
                self.logger.error(f"Unsupported operating system: {self.platform}")
                self.logger.info("The Daheng SDK is only available for Linux and Windows")
                return False
                
        except Exception as e:
            self.logger.error(f"Installation failed with unexpected error: {e}")
            return False
    
    def _install_linux(self) -> bool:
        """
        Install Daheng SDK on Linux using .run script.
        
        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Daheng Galaxy SDK for Linux")
        
        try:
            # Download and extract the SDK
            self.logger.info(f"Downloading SDK from {self.linux_sdk_url}")
            extracted_dir = download_and_extract_tarball(
                url=self.linux_sdk_url,
                extract_to=str(self.daheng_dir)
            )
            self.logger.info(f"Extracted SDK to {extracted_dir}")
            
            # Find and prepare the installer script
            # The installer might be directly in the extracted directory or in a subdirectory
            runfile_path = Path(extracted_dir) / "Galaxy_camera.run"
            
            if not runfile_path.exists():
                # Look for the installer in subdirectories
                for subdir in Path(extracted_dir).iterdir():
                    if subdir.is_dir():
                        potential_runfile = subdir / "Galaxy_camera.run"
                        if potential_runfile.exists():
                            runfile_path = potential_runfile
                            self.logger.info(f"Found installer in subdirectory: {runfile_path}")
                            break
                else:
                    self.logger.error(f"Installer script not found in {extracted_dir} or its subdirectories")
                    self.logger.debug(f"Contents of {extracted_dir}: {list(Path(extracted_dir).iterdir())}")
                    return False
            
            # Make the installer executable
            self.logger.info("Making installer script executable")
            self._make_executable(runfile_path)
            
            # Change to directory containing the installer and run installer
            original_cwd = os.getcwd()
            installer_dir = runfile_path.parent
            os.chdir(installer_dir)
            self.logger.debug(f"Changed working directory to {installer_dir}")
            
            try:
                self.logger.info("Running Galaxy SDK installer")
                self.logger.warning("The installer may require user interaction")
                
                result = subprocess.run(
                    ["./Galaxy_camera.run"],
                    cwd=installer_dir,
                    capture_output=False  # Allow user interaction
                )
                
                if result.returncode == 0:
                    self.logger.info("Daheng Galaxy SDK installation completed successfully")
                    self.logger.info("Note: You may need to install gxipy separately for Python support")
                    return True
                else:
                    self.logger.error(f"Installer failed with return code: {result.returncode}")
                    return False
                    
            finally:
                # Always restore original working directory
                os.chdir(original_cwd)
                self.logger.debug(f"Restored working directory to {original_cwd}")
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Linux installation: {e}")
            return False
    
    def _make_executable(self, file_path: Path) -> None:
        """
        Make a file executable by adding execute permissions.
        
        Args:
            file_path: Path to the file to make executable
        """
        self.logger.debug(f"Making file executable: {file_path}")
        current_mode = file_path.stat().st_mode
        new_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP
        file_path.chmod(new_mode)
        self.logger.debug(f"Changed file permissions from {oct(current_mode)} to {oct(new_mode)}")
    
    def _install_windows(self) -> bool:
        """
        Install Daheng SDK on Windows.
        
        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Daheng Galaxy SDK for Windows")
        
        # Check for administrative privileges
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        self.logger.debug(f"Administrative privileges: {is_admin}")
        
        if not is_admin:
            self.logger.warning("Administrative privileges required for Windows installation")
            return self._elevate_privileges()
        
        try:
            # Download and extract the SDK
            self.logger.info(f"Downloading SDK from {self.windows_sdk_url}")
            extracted_dir = download_and_extract_zip(
                url=self.windows_sdk_url,
                extract_to=str(self.daheng_dir)
            )
            
            # Find the SDK executable
            sdk_exe = self._find_windows_executable(extracted_dir)
            self.logger.info(f"Found SDK executable: {sdk_exe}")
            
            # Run the installer silently
            self.logger.info("Running Daheng Galaxy SDK installer")
            self.logger.info("This will also install the gxipy Python library")
            subprocess.run([sdk_exe, "/S"], check=True)
            self.logger.info("Daheng Galaxy SDK installation completed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Windows installation: {e}")
            return False
    
    def _find_windows_executable(self, extracted_dir: str) -> str:
        """
        Find the Windows SDK executable in the extracted directory.
        
        Args:
            extracted_dir: Path to extracted SDK directory
            
        Returns:
            Path to the SDK executable
            
        Raises:
            FileNotFoundError: If executable not found
        """
        if '.exe' in extracted_dir:
            return extracted_dir
        
        # Look for .exe files in the directory
        exe_files = list(Path(extracted_dir).glob("*.exe"))
        if exe_files:
            return str(exe_files[0])
        
        # Fallback to first file in directory
        contents = os.listdir(extracted_dir)
        if contents:
            return os.path.join(extracted_dir, contents[0])
        
        raise FileNotFoundError(f"No executable found in {extracted_dir}")
    
    def _elevate_privileges(self) -> bool:
        """
        Attempt to elevate privileges on Windows.
        
        Returns:
            False (elevation requires restart)
        """
        self.logger.info("Attempting to elevate privileges")
        self.logger.warning("Please restart VS Code with administrator privileges")
        
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, 
                " ".join([sys.argv[0]] + sys.argv[1:]), 
                None, 1
            )
        except Exception as e:
            self.logger.error(f"Failed to elevate process: {e}")
            self.logger.error("Please run the script in Administrator mode")
        
        return False
    
    def uninstall(self) -> bool:
        """
        Uninstall the Daheng SDK.
        
        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Starting Daheng Galaxy SDK uninstallation")
        
        try:
            if self.platform == "Linux":
                return self._uninstall_linux()
            elif self.platform == "Windows":
                return self._uninstall_windows()
            else:
                self.logger.error(f"Unsupported operating system: {self.platform}")
                return False
                
        except Exception as e:
            self.logger.error(f"Uninstallation failed with unexpected error: {e}")
            return False
    
    def _uninstall_linux(self) -> bool:
        """
        Uninstall Daheng SDK on Linux.
        
        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Uninstalling Daheng Galaxy SDK from Linux")
        
        try:
            # Remove Galaxy Camera packages
            self.logger.info("Removing galaxy-camera packages")
            subprocess.run(["sudo", "apt-get", "remove", "-y", "galaxy-camera*"], check=True)
            
            # Clean up unused packages
            self.logger.info("Cleaning up unused packages")
            subprocess.run(["sudo", "apt-get", "autoremove", "-y"], check=True)
            
            self.logger.info("Daheng Galaxy SDK uninstalled successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False
    
    def _uninstall_windows(self) -> bool:
        """
        Uninstall Daheng SDK on Windows.
        
        Returns:
            False (manual uninstallation required)
        """
        self.logger.warning("Automatic uninstallation on Windows is not yet implemented")
        self.logger.info("Please use the Windows Control Panel to uninstall the Daheng Galaxy SDK")
        return False


def install_daheng_sdk(release_version: str = "v1.0-stable") -> bool:
    """
    Install the Daheng Galaxy SDK.
    
    The Daheng SDK is required to connect and use Daheng cameras. The SDK is 
    only available for Linux and Windows.
    
    The Linux installer used here is the X86 installer. An ARM installer is 
    also available from the Daheng website, if you need to install the SDK 
    on an ARM-based system.
    
    For Windows, the SDK installer will also automatically install the 
    associated Python library, gxipy. For Linux, the gxipy library may need 
    to be installed separately after SDK installation. Note that the Windows 
    and Linux versions of gxipy are different and do not have the same API.
    
    Args:
        release_version: SDK release version to install
        
    Returns:
        True if installation successful, False otherwise
    """
    installer = DahengSDKInstaller(release_version)
    return installer.install()


def uninstall_daheng_sdk() -> bool:
    """
    Uninstall the Daheng Galaxy SDK.
    
    This function removes the Daheng SDK from the system.
    
    Returns:
        True if uninstallation successful, False otherwise
    """
    installer = DahengSDKInstaller()
    return installer.uninstall()


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Install or uninstall the Daheng Galaxy SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                    # Install Galaxy SDK
    %(prog)s --uninstall        # Uninstall Galaxy SDK
    
For more information, visit: https://www.daheng-imaging.com/
        """
    )
    parser.add_argument(
        "--uninstall", 
        action="store_true", 
        help="Uninstall the Daheng SDK instead of installing"
    )
    parser.add_argument(
        "--version",
        default="v1.0-stable",
        help="SDK release version to install (default: v1.0-stable)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Create installer to access logger
    installer = DahengSDKInstaller(args.version)
    
    # Configure logging level
    if args.verbose:
        installer.logger.setLevel(logging.DEBUG)
        installer.logger.debug("Verbose logging enabled")
    
    # Perform the requested action
    if args.uninstall:
        success = installer.uninstall()
    else:
        success = installer.install()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
