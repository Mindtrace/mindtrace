#!/usr/bin/env python3
"""Basler Pylon SDK Setup Script

This script automates the download and installation of the Basler Pylon SDK
for both Linux and Windows systems. The Pylon SDK is required to connect
and use Basler cameras in the Mindtrace hardware system.

Features:
- Automatic SDK download from GitHub releases
- Platform-specific installation (Linux .deb packages, Windows .exe)
- Dependency management for Linux systems
- Administrative privilege handling for Windows
- Comprehensive logging and error handling
- Uninstallation support

Usage:
    python setup_basler.py                    # Install SDK
    python setup_basler.py --uninstall        # Uninstall SDK
    mindtrace-setup-basler                     # Console script (install)
    mindtrace-uninstall-basler                 # Console script (uninstall)
"""

import argparse
import ctypes
import glob
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import List

from mindtrace.core import Mindtrace
from mindtrace.core.utils import download_and_extract_tarball, download_and_extract_zip
from mindtrace.hardware.core.config import get_hardware_config


class PylonSDKInstaller(Mindtrace):
    """Basler Pylon SDK installer and manager.

    This class handles the download, installation, and uninstallation of the Basler Pylon SDK across different
    platforms.
    """

    # SDK URLs for different platforms
    LINUX_SDK_URL = "https://github.com/Mindtrace/basler-sdk/releases/download/basler_sdk_linux/pylon-8.1.0_linux-x86_64_debs.tar.gz"
    WINDOWS_SDK_URL = (
        "https://github.com/Mindtrace/basler-sdk/releases/download/basler_sdk_windows/Basler.pylon.8.1.0.zip"
    )

    # Linux dependencies required for Pylon SDK
    LINUX_DEPENDENCIES = ["libglx-mesa0", "libgl1", "libxcb-xinerama0", "libxcb-xinput0", "libxcb-cursor0"]

    def __init__(self, release_version: str = "v1.0-stable"):
        """Initialize the Pylon SDK installer.

        Args:
            release_version: SDK release version to download
        """
        # Initialize base class first
        super().__init__()

        # Get hardware configuration
        self.hardware_config = get_hardware_config()

        self.release_version = release_version
        self.pylon_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "pylon"
        self.platform = platform.system()

        self.logger.info(f"Initializing Pylon SDK installer for {self.platform}")
        self.logger.debug(f"Release version: {release_version}")
        self.logger.debug(f"Installation directory: {self.pylon_dir}")

    def install(self) -> bool:
        """Install the Pylon SDK for the current platform.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Starting Pylon SDK installation")

        try:
            if self.platform == "Linux":
                return self._install_linux()
            elif self.platform == "Windows":
                return self._install_windows()
            else:
                self.logger.error(f"Unsupported operating system: {self.platform}")
                self.logger.info("The Pylon SDK is only available for Linux and Windows")
                return False

        except Exception as e:
            self.logger.error(f"Installation failed with unexpected error: {e}")
            return False

    def _install_linux(self) -> bool:
        """Install Pylon SDK on Linux using .deb packages.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Pylon SDK for Linux")

        try:
            # Download and extract the SDK
            self.logger.info(f"Downloading SDK from {self.LINUX_SDK_URL}")
            extracted_dir = download_and_extract_tarball(url=self.LINUX_SDK_URL, extract_to=str(self.pylon_dir))
            self.logger.info(f"Extracted SDK to {extracted_dir}")

            # Change to extracted directory
            original_cwd = os.getcwd()
            os.chdir(extracted_dir)
            self.logger.debug(f"Changed working directory to {extracted_dir}")

            try:
                # Install the packages
                self._install_linux_packages()
                self.logger.info("Pylon SDK installation completed successfully")
                self.logger.info("IMPORTANT: Please log out and log in again for changes to take effect")
                self.logger.info("          Also, unplug and replug all USB cameras")
                return True

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

    def _install_linux_packages(self) -> None:
        """Install the .deb packages and dependencies on Linux.

        Raises:
            subprocess.CalledProcessError: If package installation fails
            FileNotFoundError: If .deb packages not found
        """
        self.logger.info("Installing Pylon SDK using Debian packages")

        # Log current directory contents for debugging
        current_dir = os.getcwd()
        self.logger.debug(f"Current working directory: {current_dir}")

        contents = list(os.listdir("."))
        self.logger.debug(f"Directory contents: {contents}")

        # Find all pylon and codemeter deb packages
        pylon_debs = glob.glob("pylon_*.deb")
        codemeter_debs = glob.glob("codemeter*.deb")
        all_debs = pylon_debs + codemeter_debs

        self.logger.info(f"Found {len(all_debs)} .deb packages:")
        for deb in all_debs:
            self.logger.info(f"  - {deb}")

        if not all_debs:
            raise FileNotFoundError("No .deb packages found in the current directory")

        # Install dependencies first
        self.logger.info("Installing system dependencies")
        self._run_command(["sudo", "apt-get", "update"])
        self._run_command(["sudo", "apt-get", "install", "-y"] + self.LINUX_DEPENDENCIES)

        # Install all found packages using dpkg
        self.logger.info("Installing .deb packages")
        for deb in all_debs:
            self.logger.info(f"Installing {deb}")
            self._run_command(["sudo", "dpkg", "-i", deb])

        # Fix any missing dependencies
        self.logger.info("Fixing dependencies")
        self._run_command(["sudo", "apt-get", "-f", "install", "-y"])

    def _install_windows(self) -> bool:
        """Install Pylon SDK on Windows.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Pylon SDK for Windows")

        # Check for administrative privileges
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        self.logger.debug(f"Administrative privileges: {is_admin}")

        if not is_admin:
            self.logger.warning("Administrative privileges required for Windows installation")
            return self._elevate_privileges()

        try:
            # Download and extract the SDK
            self.logger.info(f"Downloading SDK from {self.WINDOWS_SDK_URL}")
            extracted_dir = download_and_extract_zip(url=self.WINDOWS_SDK_URL, extract_to=str(self.pylon_dir))

            # Find the SDK executable
            sdk_exe = self._find_windows_executable(extracted_dir)
            self.logger.info(f"Found SDK executable: {sdk_exe}")

            # Run the installer silently
            self.logger.info("Running Pylon SDK installer")
            subprocess.run([sdk_exe, "/S"], check=True)
            self.logger.info("Pylon SDK installation completed successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Windows installation: {e}")
            return False

    def _find_windows_executable(self, extracted_dir: str) -> str:
        """Find the Windows SDK executable in the extracted directory.

        Args:
            extracted_dir: Path to extracted SDK directory

        Returns:
            Path to the SDK executable

        Raises:
            FileNotFoundError: If executable not found
        """
        if ".exe" in extracted_dir:
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
        """Attempt to elevate privileges on Windows.

        Returns:
            False (elevation requires restart)
        """
        self.logger.info("Attempting to elevate privileges")
        self.logger.warning("Please restart VS Code with administrator privileges")

        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join([sys.argv[0]] + sys.argv[1:]), None, 1
            )
        except Exception as e:
            self.logger.error(f"Failed to elevate process: {e}")
            self.logger.error("Please run the script in Administrator mode")

        return False

    def _run_command(self, cmd: List[str]) -> None:
        """Run a system command with logging.

        Args:
            cmd: Command and arguments to run

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        self.logger.debug(f"Running command: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

    def uninstall(self) -> bool:
        """Uninstall the Pylon SDK.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Starting Pylon SDK uninstallation")

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
        """Uninstall Pylon SDK on Linux.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Uninstalling Pylon SDK from Linux")

        try:
            # Remove pylon packages
            self.logger.info("Removing pylon packages")
            self._run_command(["sudo", "apt-get", "remove", "-y", "pylon*"])

            # Remove codemeter packages (ignore errors)
            self.logger.info("Removing codemeter packages")
            subprocess.run(["sudo", "apt-get", "remove", "-y", "codemeter*"], check=False)

            # Clean up
            self.logger.info("Cleaning up unused packages")
            self._run_command(["sudo", "apt-get", "autoremove", "-y"])

            self.logger.info("Pylon SDK uninstalled successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    def _uninstall_windows(self) -> bool:
        """Uninstall Pylon SDK on Windows.

        Returns:
            False (manual uninstallation required)
        """
        self.logger.warning("Automatic uninstallation on Windows is not yet implemented")
        self.logger.info("Please use the Windows Control Panel to uninstall the Pylon SDK")
        return False


def install_pylon_sdk(release_version: str = "v1.0-stable") -> bool:
    """Install the Basler Pylon SDK.

    Args:
        release_version: SDK release version to install

    Returns:
        True if installation successful, False otherwise
    """
    installer = PylonSDKInstaller(release_version)
    return installer.install()


def uninstall_pylon_sdk() -> bool:
    """Uninstall the Basler Pylon SDK.

    Returns:
        True if uninstallation successful, False otherwise
    """
    installer = PylonSDKInstaller()
    return installer.uninstall()


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Install or uninstall the Basler Pylon SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                    # Install Pylon SDK
    %(prog)s --uninstall        # Uninstall Pylon SDK
    
For more information, visit: https://www.baslerweb.com/en/downloads/software-downloads/
        """,
    )
    parser.add_argument("--uninstall", action="store_true", help="Uninstall the Pylon SDK instead of installing")
    parser.add_argument(
        "--version", default="v1.0-stable", help="SDK release version to install (default: v1.0-stable)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Create installer to access logger
    installer = PylonSDKInstaller(args.version)

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
    main()  # pragma: no cover
