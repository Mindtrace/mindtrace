#!/usr/bin/env python3
"""Matrix Vision GenICam CTI Setup Script

This script automates the download and installation of the Matrix Vision
Impact Acquire SDK and GenTL Producer (CTI files) for Linux, Windows, and macOS.
The CTI files are required for GenICam camera communication via Harvesters.

Features:
- Automatic SDK download from Matrix Vision or GitHub releases
- Platform-specific installation (Linux .deb/.tar.gz, Windows .exe, macOS .dmg/.pkg)
- CTI file detection and verification
- Administrative privilege handling
- Comprehensive logging and error handling
- Uninstallation support
- Harvesters CTI path configuration

CTI File Locations:
- Linux: /opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti
- Windows: C:\\Program Files\\MATRIX VISION\\mvIMPACT Acquire\\bin\\x64\\mvGenTLProducer.cti
- macOS: /Applications/mvIMPACT_Acquire.app/Contents/Libraries/x86_64/mvGenTLProducer.cti

Usage:
    python setup_genicam.py                      # Install CTI files
    python setup_genicam.py --uninstall          # Uninstall SDK
    python setup_genicam.py --verify             # Verify CTI installation
    mindtrace-camera-genicam-install            # Console script (install)
    mindtrace-camera-genicam-uninstall          # Console script (uninstall)
    mindtrace-camera-genicam-verify             # Console script (verify)
"""

import ctypes
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import typer

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.config import get_hardware_config

# Typer app instance
app = typer.Typer(
    name="genicam-setup",
    help="Install or manage Matrix Vision GenICam CTI files",
    add_completion=False,
    rich_markup_mode="rich",
)


class GenICamCTIInstaller(Mindtrace):
    """Matrix Vision GenICam CTI installer and manager.

    This class handles the download, installation, and uninstallation of the Matrix Vision
    Impact Acquire SDK and GenTL Producer across different platforms.
    """

    # SDK URLs for different platforms (Balluff official releases)
    # Base URL for mvIMPACT Acquire SDK downloads
    BASE_SDK_URL = "https://assets-2.balluff.com/mvIMPACT_Acquire/3.6.0/"

    LINUX_SDK_URL = f"{BASE_SDK_URL}ImpactAcquire-x86_64-linux-3.6.0.sh"
    WINDOWS_SDK_URL = f"{BASE_SDK_URL}ImpactAcquire-x86_64-3.6.0.exe"
    MACOS_SDK_URL = f"{BASE_SDK_URL}ImpactAcquire-ARM64_macOS-3.6.0.dmg"

    # Platform-specific CTI file paths
    CTI_PATHS = {
        "Linux": "/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti",
        "Windows": r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64\mvGenTLProducer.cti",
        "Darwin": "/Applications/mvIMPACT_Acquire.app/Contents/Libraries/x86_64/mvGenTLProducer.cti",
    }

    # Linux dependencies required for Impact Acquire SDK
    LINUX_DEPENDENCIES = [
        "build-essential",
        "cmake",
        "libusb-1.0-0-dev",
        "libudev-dev",
        "libxml2-dev",
        "libxslt1-dev",
        "python3-dev",
    ]

    def __init__(self, release_version: str = "latest"):
        """Initialize the GenICam CTI installer.

        Args:
            release_version: SDK release version to download
        """
        # Initialize base class first
        super().__init__()

        # Get hardware configuration
        self.hardware_config = get_hardware_config()

        self.release_version = release_version
        self.impact_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "impact_acquire"
        self.platform = platform.system()

        self.logger.info(f"Initializing GenICam CTI installer for {self.platform}")
        self.logger.debug(f"Release version: {release_version}")
        self.logger.debug(f"Installation directory: {self.impact_dir}")
        self.logger.debug(f"Expected CTI path: {self.get_cti_path()}")

    def get_cti_path(self) -> str:
        """Get the expected CTI file path for the current platform.

        Returns:
            Path to the CTI file for the current platform
        """
        return self.CTI_PATHS.get(self.platform, "")

    def verify_installation(self) -> bool:
        """Verify that the CTI file is properly installed.

        Returns:
            True if CTI file exists and is accessible, False otherwise
        """
        cti_path = self.get_cti_path()
        if not cti_path:
            self.logger.error(f"No CTI path defined for platform: {self.platform}")
            return False

        self.logger.info(f"Verifying CTI installation at: {cti_path}")

        if os.path.exists(cti_path):
            self.logger.info("✓ CTI file found and accessible")

            # Additional verification - check file size (CTI files should be > 1MB)
            file_size = os.path.getsize(cti_path) / (1024 * 1024)  # MB
            if file_size > 1.0:
                self.logger.info(f"✓ CTI file size: {file_size:.2f} MB (valid)")
                return True
            else:
                self.logger.warning(f"⚠ CTI file size: {file_size:.2f} MB (may be corrupted)")
                return False
        else:
            self.logger.error("✗ CTI file not found")
            return False

    def install(self) -> bool:
        """Install the Matrix Vision Impact Acquire SDK for the current platform.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Starting Matrix Vision Impact Acquire SDK installation")

        try:
            if self.platform == "Linux":
                return self._install_linux()
            elif self.platform == "Windows":
                return self._install_windows()
            elif self.platform == "Darwin":
                return self._install_macos()
            else:
                self.logger.error(f"Unsupported operating system: {self.platform}")
                self.logger.info("The Impact Acquire SDK is only available for Linux, Windows, and macOS")
                return False

        except Exception as e:
            self.logger.error(f"Installation failed with unexpected error: {e}")
            return False

    def _install_linux(self) -> bool:
        """Install Impact Acquire SDK on Linux.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Matrix Vision Impact Acquire SDK for Linux")

        try:
            # Install dependencies first
            self.logger.info("Installing system dependencies")
            self._run_command(["sudo", "apt-get", "update"])
            self._run_command(["sudo", "apt-get", "install", "-y"] + self.LINUX_DEPENDENCIES)

            # Download the installer script
            self.logger.info(f"Downloading installer from {self.LINUX_SDK_URL}")
            installer_path = self.impact_dir / "ImpactAcquire-installer.sh"
            self.impact_dir.mkdir(parents=True, exist_ok=True)

            # Download the installer script
            import urllib.request

            urllib.request.urlretrieve(self.LINUX_SDK_URL, installer_path)
            self.logger.info(f"Downloaded installer to {installer_path}")

            # Make installer executable
            self._run_command(["chmod", "+x", str(installer_path)])

            # Run the installer script
            self.logger.info("Running Impact Acquire installer")
            self.logger.info("NOTE: This may take several minutes and will prompt for installation options")

            # Run installer with sudo (it needs root permissions)
            self._run_command(["sudo", "bash", str(installer_path)])

            # Verify installation
            if self.verify_installation():
                self.logger.info("Matrix Vision Impact Acquire SDK installation completed successfully")
                self.logger.info("IMPORTANT: Please log out and log in again for changes to take effect")
                self.logger.info("          Also, unplug and replug all GenICam cameras")
                return True
            else:
                self.logger.error("Installation completed but CTI verification failed")
                return False

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Linux installation: {e}")
            return False

    def _find_install_script(self) -> Optional[str]:
        """Find the installation script in the extracted directory.

        Returns:
            Path to installation script if found, None otherwise
        """
        possible_scripts = ["install.sh", "setup.sh", "install_mvIMPACT_Acquire.sh"]

        for script in possible_scripts:
            if os.path.exists(script):
                self.logger.debug(f"Found installation script: {script}")
                return script

        self.logger.warning("No installation script found, using manual installation")
        return None

    def _install_linux_manual(self) -> None:
        """Manual installation for Linux when no script is available."""
        self.logger.info("Performing manual Linux installation")

        # Look for .deb packages
        deb_files = list(Path(".").glob("*.deb"))
        if deb_files:
            self.logger.info(f"Installing {len(deb_files)} .deb packages")
            for deb_file in deb_files:
                self.logger.info(f"Installing {deb_file}")
                self._run_command(["sudo", "dpkg", "-i", str(deb_file)])

            # Fix dependencies
            self._run_command(["sudo", "apt-get", "-f", "install", "-y"])
        else:
            # Copy files manually to /opt/ImpactAcquire
            self.logger.info("Copying files to /opt/ImpactAcquire")
            target_dir = Path("/opt/ImpactAcquire")

            # Create target directory
            self._run_command(["sudo", "mkdir", "-p", str(target_dir)])

            # Copy all contents
            self._run_command(["sudo", "cp", "-r", ".", str(target_dir / "sdk")])

            # Set permissions
            self._run_command(["sudo", "chmod", "-R", "755", str(target_dir)])

    def _install_windows(self) -> bool:
        """Install Impact Acquire SDK on Windows.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Matrix Vision Impact Acquire SDK for Windows")

        # Check for administrative privileges
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        self.logger.debug(f"Administrative privileges: {is_admin}")

        if not is_admin:
            self.logger.warning("Administrative privileges required for Windows installation")
            return self._elevate_privileges()

        try:
            # Download the SDK installer
            self.logger.info(f"Downloading installer from {self.WINDOWS_SDK_URL}")

            installer_file = self.impact_dir / "ImpactAcquire-installer.exe"
            self.impact_dir.mkdir(parents=True, exist_ok=True)

            # Download the installer
            import urllib.request

            urllib.request.urlretrieve(self.WINDOWS_SDK_URL, installer_file)
            self.logger.info(f"Downloaded installer to: {installer_file}")

            # Run the installer (may require user interaction)
            self.logger.info("Running Impact Acquire SDK installer")
            self.logger.info("NOTE: You may need to follow installer prompts")
            subprocess.run([str(installer_file)], check=True)

            # Verify installation
            if self.verify_installation():
                self.logger.info("Matrix Vision Impact Acquire SDK installation completed successfully")
                return True
            else:
                self.logger.error("Installation completed but CTI verification failed")
                return False

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Windows installation: {e}")
            return False

    def _install_macos(self) -> bool:
        """Install Impact Acquire SDK on macOS.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Matrix Vision Impact Acquire SDK for macOS")

        try:
            # Download the SDK installer
            self.logger.info(f"Downloading installer from {self.MACOS_SDK_URL}")

            # For .dmg files, we need to mount and extract
            dmg_file = self.impact_dir / "ImpactAcquire.dmg"
            self.impact_dir.mkdir(parents=True, exist_ok=True)

            # Download DMG
            import urllib.request

            urllib.request.urlretrieve(self.MACOS_SDK_URL, dmg_file)
            self.logger.info(f"Downloaded DMG to: {dmg_file}")

            # Mount the DMG
            self.logger.info("Mounting DMG file")
            mount_result = subprocess.run(
                ["hdiutil", "attach", str(dmg_file), "-readonly", "-nobrowse"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Extract mount point from output
            mount_point = None
            for line in mount_result.stdout.split("\n"):
                if "/Volumes/" in line:
                    mount_point = line.split("\t")[-1].strip()
                    break

            if not mount_point:
                raise RuntimeError("Failed to find mount point for DMG")

            self.logger.info(f"DMG mounted at: {mount_point}")

            try:
                # Look for installer package or app
                mount_path = Path(mount_point)
                pkg_files = list(mount_path.glob("*.pkg"))
                app_files = list(mount_path.glob("*.app"))

                if pkg_files:
                    # Install .pkg file
                    pkg_file = pkg_files[0]
                    self.logger.info(f"Installing package: {pkg_file}")
                    subprocess.run(["sudo", "installer", "-pkg", str(pkg_file), "-target", "/"], check=True)
                elif app_files:
                    # Copy .app to Applications
                    app_file = app_files[0]
                    target_app = Path("/Applications") / app_file.name
                    self.logger.info(f"Copying {app_file.name} to Applications")

                    if target_app.exists():
                        shutil.rmtree(target_app)
                    shutil.copytree(app_file, target_app)
                else:
                    raise FileNotFoundError("No .pkg or .app files found in DMG")

            finally:
                # Unmount the DMG
                self.logger.info("Unmounting DMG")
                subprocess.run(["hdiutil", "detach", mount_point], check=False)

            # Verify installation
            if self.verify_installation():
                self.logger.info("Matrix Vision Impact Acquire SDK installation completed successfully")
                return True
            else:
                self.logger.error("Installation completed but CTI verification failed")
                return False

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during macOS installation: {e}")
            return False

    def _elevate_privileges(self) -> bool:
        """Attempt to elevate privileges on Windows.

        Returns:
            False (elevation requires restart)
        """
        self.logger.info("Attempting to elevate privileges")
        self.logger.warning("Please restart the application with administrator privileges")

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
        """Uninstall the Impact Acquire SDK.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Starting Matrix Vision Impact Acquire SDK uninstallation")

        try:
            if self.platform == "Linux":
                return self._uninstall_linux()
            elif self.platform == "Windows":
                return self._uninstall_windows()
            elif self.platform == "Darwin":
                return self._uninstall_macos()
            else:
                self.logger.error(f"Unsupported operating system: {self.platform}")
                return False

        except Exception as e:
            self.logger.error(f"Uninstallation failed with unexpected error: {e}")
            return False

    def _uninstall_linux(self) -> bool:
        """Uninstall Impact Acquire SDK on Linux.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Uninstalling Matrix Vision Impact Acquire SDK from Linux")

        try:
            # Remove installed packages
            self.logger.info("Removing mvimpact packages")
            subprocess.run(["sudo", "apt-get", "remove", "-y", "mvimpact*"], check=False)

            # Remove installation directory
            if os.path.exists("/opt/ImpactAcquire"):
                self.logger.info("Removing /opt/ImpactAcquire directory")
                self._run_command(["sudo", "rm", "-rf", "/opt/ImpactAcquire"])

            # Clean up
            self.logger.info("Cleaning up unused packages")
            self._run_command(["sudo", "apt-get", "autoremove", "-y"])

            self.logger.info("Matrix Vision Impact Acquire SDK uninstalled successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    def _uninstall_windows(self) -> bool:
        """Uninstall Impact Acquire SDK on Windows.

        Returns:
            False (manual uninstallation required)
        """
        self.logger.warning("Automatic uninstallation on Windows is not yet implemented")
        self.logger.info("Please use the Windows Control Panel to uninstall the Impact Acquire SDK")
        return False

    def _uninstall_macos(self) -> bool:
        """Uninstall Impact Acquire SDK on macOS.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Uninstalling Matrix Vision Impact Acquire SDK from macOS")

        try:
            # Remove application
            app_path = "/Applications/mvIMPACT_Acquire.app"
            if os.path.exists(app_path):
                self.logger.info(f"Removing {app_path}")
                shutil.rmtree(app_path)

            # Remove any other installation directories
            possible_dirs = ["/usr/local/lib/mvIMPACT_Acquire", "/opt/mvIMPACT_Acquire"]

            for dir_path in possible_dirs:
                if os.path.exists(dir_path):
                    self.logger.info(f"Removing {dir_path}")
                    subprocess.run(["sudo", "rm", "-rf", dir_path], check=False)

            self.logger.info("Matrix Vision Impact Acquire SDK uninstalled successfully")
            return True

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False


def install_genicam_cti(release_version: str = "latest") -> bool:
    """Install the Matrix Vision GenICam CTI files.

    Args:
        release_version: SDK release version to install

    Returns:
        True if installation successful, False otherwise
    """
    installer = GenICamCTIInstaller(release_version)
    return installer.install()


def uninstall_genicam_cti() -> bool:
    """Uninstall the Matrix Vision Impact Acquire SDK.

    Returns:
        True if uninstallation successful, False otherwise
    """
    installer = GenICamCTIInstaller()
    return installer.uninstall()


def verify_genicam_cti() -> bool:
    """Verify the Matrix Vision CTI installation.

    Returns:
        True if CTI files are properly installed, False otherwise
    """
    installer = GenICamCTIInstaller()
    return installer.verify_installation()


@app.command()
def install(
    version: str = typer.Option(
        "latest",
        "--version",
        help="SDK release version to install",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Install the Matrix Vision Impact Acquire SDK and CTI files.

    Downloads and installs the SDK from the official Balluff/Matrix Vision servers.
    The CTI files are required for GenICam camera communication via Harvesters.
    """
    installer = GenICamCTIInstaller(version)

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.install()
    raise typer.Exit(code=0 if success else 1)


@app.command()
def uninstall(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Uninstall the Matrix Vision Impact Acquire SDK."""
    installer = GenICamCTIInstaller()

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.uninstall()

    if success:
        typer.echo("✓ Matrix Vision Impact Acquire SDK uninstalled successfully")
    else:
        typer.echo("✗ Matrix Vision Impact Acquire SDK uninstallation failed", err=True)

    raise typer.Exit(code=0 if success else 1)


@app.command()
def verify(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Verify that CTI files are properly installed."""
    installer = GenICamCTIInstaller()

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.verify_installation()

    if success:
        typer.echo("✓ Matrix Vision CTI verification successful")
    else:
        typer.echo("✗ Matrix Vision CTI verification failed", err=True)

    raise typer.Exit(code=0 if success else 1)


def main() -> None:
    """Main entry point for the script."""
    app()


if __name__ == "__main__":
    main()
