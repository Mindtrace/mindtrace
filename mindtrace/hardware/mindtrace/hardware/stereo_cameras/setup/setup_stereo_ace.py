#!/usr/bin/env python3
"""Basler Stereo ace Setup Script

This script automates the download and installation of the Basler pylon Supplementary Package
for Stereo ace cameras on Linux systems. The package provides the GenTL Producer needed
to connect and use Stereo ace camera systems in the Mindtrace hardware system.

Features:
- Automatic package download from Basler or custom URL
- Supports both Debian package (.deb) and tar.gz archive installation
- Custom installation path support (default: ~/.local/share/pylon_stereo)
- Environment variable setup for GenTL Producer
- Shell environment script generation
- Comprehensive logging and error handling
- Uninstallation support

Installation Methods:
    1. Debian Package (Recommended - requires sudo):
       - Installs to /opt/pylon
       - Automatic environment configuration
       - System-wide availability

    2. tar.gz Archive (Portable - no sudo):
       - Installs to user-specified or default directory
       - Requires manual environment setup
       - Per-user installation

Usage:
    python setup_stereo_ace.py                           # Install with defaults
    python setup_stereo_ace.py --method deb              # Use Debian package
    python setup_stereo_ace.py --method tarball          # Use tar.gz archive
    python setup_stereo_ace.py --install-dir ~/pylon     # Custom install location
    python setup_stereo_ace.py --uninstall               # Uninstall
    mindtrace-stereo-basler-install                      # Console script (install)
    mindtrace-stereo-basler-uninstall                    # Console script (uninstall)

Environment Setup:
    After installation, you must set environment variables:

    For Debian package:
        source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon

    For tar.gz archive:
        source <install-dir>/setup_stereo_env.sh

    Or add to ~/.bashrc for persistence:
        echo "source <install-dir>/setup_stereo_env.sh" >> ~/.bashrc
"""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from mindtrace.core import Mindtrace
from mindtrace.core.utils import download_and_extract_tarball
from mindtrace.hardware.core.config import get_hardware_config


class StereoAceInstaller(Mindtrace):
    """Basler Stereo ace Supplementary Package installer and manager.

    This class handles the download, installation, and uninstallation of the
    Stereo ace Supplementary Package across different installation methods.
    """

    # Package URLs - GitHub releases for automatic download
    GITHUB_TARBALL_URL = "https://github.com/Mindtrace/basler-sdk/releases/download/stereo_ace_v1.0.3/pylon-supplementary-package-for-stereo-ace-1.0.3-Linux_x86_64_setup.tar.gz"
    GITHUB_DEB_URL = "https://github.com/Mindtrace/basler-sdk/releases/download/stereo_ace_v1.0.3/pylon-supplementary-package-for-stereo-ace-1.0.3_amd64.deb"

    # Fallback: Basler official download pages (manual download)
    BASLER_DEB_URL = "https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-debian/"
    BASLER_TARBALL_URL = "https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-setup-tar-gz/"

    # Package file names
    DEB_PACKAGE_NAME = "pylon-supplementary-package-for-stereo-ace-1.0.3_amd64.deb"
    TARBALL_PACKAGE_NAME = "pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64_setup.tar.gz"
    INNER_TARBALL_NAME = "pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64.tar.gz"

    def __init__(
        self,
        installation_method: str = "tarball",
        install_dir: Optional[str] = None,
        package_path: Optional[str] = None,
    ):
        """Initialize the Stereo ace installer.

        Args:
            installation_method: Installation method ("deb" or "tarball")
            install_dir: Custom installation directory (for tarball method)
            package_path: Path to downloaded package file (optional)
        """
        super().__init__()

        self.hardware_config = get_hardware_config()
        self.platform = platform.system()

        if self.platform != "Linux":
            raise RuntimeError("Stereo ace Supplementary Package is only supported on Linux")

        self.installation_method = installation_method

        # Set installation directory
        if install_dir:
            self.install_dir = Path(install_dir).expanduser()
        else:
            if installation_method == "deb":
                self.install_dir = Path("/opt/pylon")
            else:
                # Default to user's local directory
                self.install_dir = Path.home() / ".local" / "share" / "pylon_stereo"

        self.package_path = Path(package_path) if package_path else None

        self.logger.info(f"Initializing Stereo ace installer for {self.platform}")
        self.logger.info(f"Installation method: {installation_method}")
        self.logger.info(f"Installation directory: {self.install_dir}")

    def install(self) -> bool:
        """Install the Stereo ace Supplementary Package.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Starting Stereo ace Supplementary Package installation")

        try:
            if self.installation_method == "deb":
                return self._install_debian_package()
            elif self.installation_method == "tarball":
                return self._install_tarball()
            else:
                self.logger.error(f"Unknown installation method: {self.installation_method}")
                return False

        except Exception as e:
            self.logger.error(f"Installation failed with unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _install_debian_package(self) -> bool:
        """Install using Debian package (.deb).

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Stereo ace package using Debian package")

        # Download package if not provided
        if not self.package_path or not self.package_path.exists():
            self.logger.info("Package not provided, downloading from GitHub...")
            try:
                from mindtrace.core.utils import download_file

                # Download to temporary location
                download_dir = self.install_dir / "downloads"
                download_dir.mkdir(parents=True, exist_ok=True)

                self.logger.info(f"Downloading from {self.GITHUB_DEB_URL}")
                downloaded_path = download_file(
                    url=self.GITHUB_DEB_URL,
                    destination=str(download_dir / self.DEB_PACKAGE_NAME)
                )
                self.package_path = Path(downloaded_path)
                self.logger.info(f"Downloaded to {self.package_path}")

            except Exception as e:
                self.logger.error(f"Failed to download package: {e}")
                self.logger.info(f"Please download manually from:")
                self.logger.info(f"  {self.BASLER_DEB_URL}")
                self.logger.info(f"Then run: python setup_stereo_ace.py --method deb --package /path/to/{self.DEB_PACKAGE_NAME}")
                return False

        try:
            # Install using apt-get
            self.logger.info(f"Installing {self.package_path}")
            cmd = ["sudo", "apt-get", "install", "-y", str(self.package_path)]
            self.logger.debug(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

            self.logger.info("✅ Stereo ace Supplementary Package installed successfully!")
            self.logger.info("")
            self.logger.info("IMPORTANT: Environment setup required")
            self.logger.info("  The environment will be set automatically after logout/login.")
            self.logger.info("  Or run immediately:")
            self.logger.info("    source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon")
            self.logger.info("")
            self.logger.info("  To make persistent, add to ~/.bashrc:")
            self.logger.info("    echo 'source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon' >> ~/.bashrc")

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Debian package installation failed: {e}")
            self.logger.error("Make sure you have sudo privileges")
            return False

    def _install_tarball(self) -> bool:
        """Install using tar.gz archive.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Stereo ace package using tar.gz archive")

        # Download package if not provided
        if not self.package_path or not self.package_path.exists():
            self.logger.info("Package not provided, downloading from GitHub...")
            try:
                # Download and extract directly
                self.logger.info(f"Downloading from {self.GITHUB_TARBALL_URL}")
                extracted_dir = download_and_extract_tarball(
                    url=self.GITHUB_TARBALL_URL,
                    extract_to=str(self.install_dir / "temp_download")
                )
                self.logger.info(f"Downloaded and extracted to {extracted_dir}")

                # The extracted directory contains the setup archive, find the inner tarball
                temp_dir = Path(extracted_dir)
                inner_tarball = None

                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith(".tar.gz") and "pylon-supplementary" in file:
                            inner_tarball = Path(root) / file
                            break
                    if inner_tarball:
                        break

                if not inner_tarball:
                    self.logger.error("Could not find inner tarball in downloaded package")
                    return False

                # Use the found inner tarball
                self.package_path = inner_tarball
                self.logger.info(f"Found inner tarball: {self.package_path}")

            except Exception as e:
                self.logger.error(f"Failed to download package: {e}")
                self.logger.info(f"Please download manually from:")
                self.logger.info(f"  {self.BASLER_TARBALL_URL}")
                self.logger.info(f"Then run: python setup_stereo_ace.py --method tarball --package /path/to/{self.TARBALL_PACKAGE_NAME}")
                import traceback
                traceback.print_exc()
                return False

        try:
            # Create installation directory
            self.install_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Installation directory: {self.install_dir}")

            # Check if package_path is the outer archive or inner tarball
            import tarfile

            # If it's the setup archive (contains inner tarball), extract it first
            if "setup" in self.package_path.name.lower():
                self.logger.info(f"Extracting setup archive {self.package_path.name}")
                with tarfile.open(self.package_path, "r:gz") as tar:
                    tar.extractall(path=self.install_dir / "temp_extract")

                # Find the inner tarball
                temp_dir = self.install_dir / "temp_extract"
                inner_tarball = None

                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith(".tar.gz") and "pylon-supplementary" in file and "setup" not in file.lower():
                            inner_tarball = Path(root) / file
                            break
                    if inner_tarball:
                        break

                if not inner_tarball:
                    self.logger.error("Could not find inner tarball in package")
                    return False

                self.logger.info(f"Found inner tarball: {inner_tarball.name}")
            else:
                # It's already the inner tarball
                inner_tarball = self.package_path
                temp_dir = None

            # Extract inner tarball directly to install_dir
            self.logger.info(f"Extracting {inner_tarball.name} to {self.install_dir}")
            with tarfile.open(inner_tarball, "r:gz") as tar:
                tar.extractall(path=self.install_dir)

            # Clean up temporary extraction directory if we created one
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
                self.logger.info("Cleaned up temporary files")

            # Verify installation
            gentl_path = self.install_dir / "pylon" / "lib" / "gentlproducer" / "gtl" / "basler_xw.cti"
            if not gentl_path.exists():
                self.logger.error(f"GenTL producer not found at expected location: {gentl_path}")
                return False

            self.logger.info(f"✅ GenTL producer found: {gentl_path}")

            # Create environment setup script
            self._create_environment_script()

            # Offer to add to bashrc
            self._offer_bashrc_setup()

            self.logger.info("")
            self.logger.info("✅ Stereo ace Supplementary Package installed successfully!")
            self.logger.info("")
            self.logger.info("IMPORTANT: Environment setup required for current shell")
            self.logger.info(f"  Run this command:")
            self.logger.info(f"    source {self.install_dir}/setup_stereo_env.sh")
            self.logger.info("")
            self.logger.info("  Verify installation:")
            self.logger.info("    echo $GENICAM_GENTL64_PATH")
            self.logger.info(f"    # Should contain: {self.install_dir}/pylon/lib/gentlproducer/gtl")

            return True

        except Exception as e:
            self.logger.error(f"tar.gz installation failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _create_environment_script(self) -> None:
        """Create shell environment setup script."""
        pylon_root = self.install_dir / "pylon"
        script_path = self.install_dir / "setup_stereo_env.sh"

        script_content = f"""#!/bin/bash
# Environment setup for Basler Stereo ace cameras
# Generated by MindTrace Stereo ace installer

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PYLON_ROOT="${{SCRIPT_DIR}}/pylon"

# Set up pylon environment if pylon-setup-env.sh exists
if [ -f "${{PYLON_ROOT}}/bin/pylon-setup-env.sh" ]; then
    source "${{PYLON_ROOT}}/bin/pylon-setup-env.sh" "${{PYLON_ROOT}}"
fi

# Add Stereo ace GenTL producer path
export GENICAM_GENTL64_PATH="${{PYLON_ROOT}}/lib/gentlproducer/gtl:${{GENICAM_GENTL64_PATH}}"

# Add to LD_LIBRARY_PATH for runtime library loading
export LD_LIBRARY_PATH="${{PYLON_ROOT}}/lib:${{PYLON_ROOT}}/lib/gentlproducer/gtl:${{LD_LIBRARY_PATH}}"

echo "Basler Stereo ace environment configured:"
echo "  PYLON_ROOT: ${{PYLON_ROOT}}"
echo "  GENICAM_GENTL64_PATH: ${{GENICAM_GENTL64_PATH}}"
echo ""
echo "Stereo ace components available:"
echo "  - StereoViewer: ${{PYLON_ROOT}}/bin/StereoViewer"
echo "  - Python Samples: ${{PYLON_ROOT}}/share/pylon/Samples/Stereo_ace/Python"
echo "  - Documentation: ${{PYLON_ROOT}}/share/pylon/doc/stereo-ace/"
"""

        with open(script_path, "w") as f:
            f.write(script_content)

        # Make script executable
        script_path.chmod(0o755)
        self.logger.info(f"Created environment setup script: {script_path}")

    def _offer_bashrc_setup(self) -> None:
        """Offer to add environment setup to ~/.bashrc automatically."""
        bashrc_path = Path.home() / ".bashrc"
        script_path = self.install_dir / "setup_stereo_env.sh"
        source_line = f"source {script_path}"

        # Check if already in bashrc
        if bashrc_path.exists():
            with open(bashrc_path, "r") as f:
                bashrc_content = f.read()
                if str(script_path) in bashrc_content:
                    self.logger.info("✅ Environment setup already in ~/.bashrc")
                    return

        # Check if running in interactive terminal
        if sys.stdin.isatty():
            self.logger.info("")
            response = input(f"Add environment setup to ~/.bashrc? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                try:
                    with open(bashrc_path, "a") as f:
                        f.write(f"\n# Basler Stereo ace environment (added by mindtrace)\n")
                        f.write(f"{source_line}\n")
                    self.logger.info(f"✅ Added to ~/.bashrc")
                    self.logger.info("   Changes will take effect in new terminal sessions")
                except Exception as e:
                    self.logger.error(f"Failed to update ~/.bashrc: {e}")
            else:
                self.logger.info("Skipped ~/.bashrc setup")
                self.logger.info(f"To add manually: echo '{source_line}' >> ~/.bashrc")
        else:
            # Non-interactive mode - just inform user
            self.logger.info("")
            self.logger.info("To make environment persistent across sessions:")
            self.logger.info(f"  echo '{source_line}' >> ~/.bashrc")

    def uninstall(self) -> bool:
        """Uninstall the Stereo ace Supplementary Package.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Starting Stereo ace Supplementary Package uninstallation")

        try:
            if self.installation_method == "deb":
                return self._uninstall_debian_package()
            elif self.installation_method == "tarball":
                return self._uninstall_tarball()
            else:
                self.logger.error(f"Unknown installation method: {self.installation_method}")
                return False

        except Exception as e:
            self.logger.error(f"Uninstallation failed with unexpected error: {e}")
            return False

    def _uninstall_debian_package(self) -> bool:
        """Uninstall Debian package.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Uninstalling Stereo ace Debian package")

        try:
            # Remove package using apt-get
            cmd = ["sudo", "apt-get", "remove", "-y", "pylon-supplementary-package-for-stereo-ace"]
            self.logger.debug(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

            self.logger.info("✅ Stereo ace Supplementary Package uninstalled successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    def _uninstall_tarball(self) -> bool:
        """Uninstall tar.gz archive installation.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info(f"Uninstalling Stereo ace from {self.install_dir}")

        if not self.install_dir.exists():
            self.logger.warning(f"Installation directory not found: {self.install_dir}")
            return True

        try:
            # Remove installation directory
            shutil.rmtree(self.install_dir)
            self.logger.info(f"Removed {self.install_dir}")

            self.logger.info("✅ Stereo ace Supplementary Package uninstalled successfully")
            self.logger.info("")
            self.logger.info("Don't forget to remove the environment setup from ~/.bashrc if you added it")
            return True

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False


def install_stereo_ace() -> None:
    """CLI entry point for installation."""
    # Parse arguments for install mode
    parser = argparse.ArgumentParser(
        description="Install the Basler Stereo ace Supplementary Package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Automatic download from GitHub (default)
    %(prog)s

    # Custom installation directory
    %(prog)s --install-dir ~/my_stereo

    # Use Debian package
    %(prog)s --method deb

    # Install from local package file
    %(prog)s --package /path/to/pylon-supplementary-package-for-stereo-ace-1.0.3-Linux_x86_64_setup.tar.gz

Download packages from:
    Debian: https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-debian/
    tar.gz: https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-setup-tar-gz/
        """,
    )
    parser.add_argument(
        "--method",
        choices=["deb", "tarball"],
        default="tarball",
        help="Installation method (default: tarball)"
    )
    parser.add_argument(
        "--package",
        help="Path to downloaded package file (.deb or .tar.gz)"
    )
    parser.add_argument(
        "--install-dir",
        help="Custom installation directory (for tarball method, default: ~/.local/share/pylon_stereo)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Create installer
    installer = StereoAceInstaller(
        installation_method=args.method,
        install_dir=args.install_dir,
        package_path=args.package,
    )

    # Configure logging
    if args.verbose:
        installer.logger.setLevel(logging.DEBUG)

    # Install
    success = installer.install()
    sys.exit(0 if success else 1)


def uninstall_stereo_ace() -> None:
    """CLI entry point for uninstallation."""
    # Parse arguments for uninstall mode
    parser = argparse.ArgumentParser(
        description="Uninstall the Basler Stereo ace Supplementary Package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--method",
        choices=["deb", "tarball"],
        default="tarball",
        help="Installation method (default: tarball)"
    )
    parser.add_argument(
        "--install-dir",
        help="Custom installation directory (for tarball method, default: ~/.local/share/pylon_stereo)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Create installer
    installer = StereoAceInstaller(
        installation_method=args.method,
        install_dir=args.install_dir,
    )

    # Configure logging
    if args.verbose:
        installer.logger.setLevel(logging.DEBUG)

    # Uninstall
    success = installer.uninstall()
    sys.exit(0 if success else 1)


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Install or uninstall the Basler Stereo ace Supplementary Package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Debian package installation (requires sudo)
    %(prog)s --method deb --package pylon-supplementary-package-for-stereo-ace-1.0.3_amd64.deb

    # tar.gz archive installation (no sudo, custom directory)
    %(prog)s --method tarball --package pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64_setup.tar.gz
    %(prog)s --method tarball --package stereo.tar.gz --install-dir ~/basler_stereo

    # Uninstall
    %(prog)s --uninstall --method tarball --install-dir ~/basler_stereo

Download packages from:
    Debian: https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-debian/
    tar.gz: https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-setup-tar-gz/
        """,
    )

    parser.add_argument(
        "--method",
        choices=["deb", "tarball"],
        default="tarball",
        help="Installation method (default: tarball)"
    )
    parser.add_argument(
        "--package",
        help="Path to downloaded package file (.deb or .tar.gz)"
    )
    parser.add_argument(
        "--install-dir",
        help="Custom installation directory (for tarball method, default: ~/.local/share/pylon_stereo)"
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall instead of install"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Create installer
    installer = StereoAceInstaller(
        installation_method=args.method,
        install_dir=args.install_dir,
        package_path=args.package,
    )

    # Configure logging
    if args.verbose:
        installer.logger.setLevel(logging.DEBUG)
        installer.logger.debug("Verbose logging enabled")

    # Perform action
    if args.uninstall:
        success = installer.uninstall()
    else:
        success = installer.install()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
