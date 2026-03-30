#!/usr/bin/env python3
"""Photoneo 3D Scanner SDK Setup Script

This script automates the setup of the Photoneo 3D scanner environment.
Photoneo scanners use GigE Vision protocol and require the Matrix Vision
mvGenTL Producer for communication via Harvesters.

Based on: https://github.com/photoneo-3d/photoneo-python-examples

Supports: Linux (x86_64, aarch64), Windows (x64), macOS (ARM64, x86_64)

Requirements:
- Matrix Vision mvGenTL Producer (version 2.49.0 recommended)
- Harvesters library: pip install harvesters
- PhoXi firmware version 1.13.0 or later

Usage:
    mindtrace-scanner-photoneo install    # Install Matrix Vision SDK
    mindtrace-scanner-photoneo verify     # Verify installation
    mindtrace-scanner-photoneo discover   # Test device discovery
    mindtrace-scanner-photoneo uninstall  # Uninstall SDK
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

import typer

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.config import get_hardware_config

# Typer app instance
app = typer.Typer(
    name="photoneo-setup",
    help="Install and manage Photoneo 3D scanner SDK dependencies (Matrix Vision mvGenTL)",
    add_completion=False,
    rich_markup_mode="rich",
)


class PhotoneoSetup(Mindtrace):
    """Photoneo 3D scanner SDK setup and verification.

    This class handles the installation of the Matrix Vision mvGenTL Producer
    required for Photoneo 3D scanner communication via GigE Vision.

    Based on Photoneo's official recommendations:
    https://github.com/photoneo-3d/photoneo-python-examples
    """

    # Matrix Vision mvGenTL Producer download URLs (version 2.49.0)
    # Using assets-2.balluff.com directly (static.matrix-vision.com redirects here)
    MVGENTL_VERSION = "2.49.0"
    MVGENTL_BASE_URL = "https://assets-2.balluff.com/mvIMPACT_Acquire/2.49.0/"

    LINUX_INSTALLER_URL = f"{MVGENTL_BASE_URL}install_mvGenTL_Acquire.sh"
    LINUX_ARCHIVE_URL = f"{MVGENTL_BASE_URL}mvGenTL_Acquire-x86_64_ABI2-{MVGENTL_VERSION}.tgz"
    WINDOWS_INSTALLER_URL = f"{MVGENTL_BASE_URL}mvGenTL_Acquire-x86_64-{MVGENTL_VERSION}.exe"
    MACOS_DMG_URL = f"{MVGENTL_BASE_URL}mvGenTL_Acquire-ARM64_macOS-{MVGENTL_VERSION}.dmg"

    # Platform-specific CTI file search paths (checked in order)
    CTI_SEARCH_PATHS: Dict[str, List[str]] = {
        "Linux": [
            "/opt/mvIMPACT_Acquire/lib/x86_64/mvGenTLProducer.cti",
            "/opt/mvIMPACT_Acquire/lib/x86_64/libmvGenTLProducer.cti",
            "/opt/mvIMPACT_Acquire/lib/x86_64/libmvGenTLProducer.so",
            "/opt/mvIMPACT_Acquire/lib/arm64/mvGenTLProducer.cti",
            "/opt/mvIMPACT_Acquire/lib/arm64/libmvGenTLProducer.cti",
            "/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti",
            "/opt/ImpactAcquire/lib/arm64/mvGenTLProducer.cti",
            "/usr/lib/mvimpact-acquire/mvGenTLProducer.cti",
        ],
        "Windows": [
            r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64\mvGenTLProducer.cti",
        ],
        "Darwin": [
            "/Library/Frameworks/mvGenTLProducer.framework/Versions/Current/lib/mvGenTLProducer.cti",
            "/Applications/mvIMPACT_Acquire.app/Contents/Libraries/arm64/mvGenTLProducer.cti",
            "/Applications/mvIMPACT_Acquire.app/Contents/Libraries/x86_64/mvGenTLProducer.cti",
            "/opt/mvIMPACT_Acquire/lib/arm64/mvGenTLProducer.cti",
        ],
    }

    # GenTL env path directories per platform (for post-install env setup)
    GENTL_ENV_PATHS: Dict[str, str] = {
        "Linux": "/opt/mvIMPACT_Acquire/lib/x86_64",
        "Windows": r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64",
        "Darwin": "/Library/Frameworks/mvGenTLProducer.framework/Versions/Current/lib",
    }

    def __init__(self):
        """Initialize Photoneo setup."""
        super().__init__()
        self.hardware_config = get_hardware_config()
        self.platform = platform.system()
        self.machine = platform.machine()
        self.download_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "mvgentl"
        self.logger.info(f"Initializing Photoneo setup for {self.platform} ({self.machine})")

    # =========================================================================
    # Helpers
    # =========================================================================

    def _run_command(self, cmd: List[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
        """Run a system command with logging.

        Args:
            cmd: Command and arguments to run
            check: Whether to raise on non-zero exit
            **kwargs: Additional arguments for subprocess.run

        Returns:
            CompletedProcess result

        Raises:
            subprocess.CalledProcessError: If command fails and check=True
        """
        self.logger.debug(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, check=check, **kwargs)

    def _download_file(self, url: str, dest: Path, description: str = "file") -> bool:
        """Download a file with redirect handling, progress logging, and retry.

        Args:
            url: URL to download from
            dest: Destination file path
            description: Human-readable description for logging

        Returns:
            True if download successful
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"Downloading {description} (attempt {attempt}/{max_retries})")
                self.logger.debug(f"URL: {url}")
                self.logger.debug(f"Destination: {dest}")

                request = urllib.request.Request(url, headers={"User-Agent": "mindtrace-setup/1.0"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    total_size = int(response.headers.get("Content-Length", 0))
                    if total_size:
                        self.logger.info(f"Download size: {total_size / (1024 * 1024):.1f} MB")

                    with open(dest, "wb") as f:
                        downloaded = 0
                        chunk_size = 64 * 1024
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)

                # Verify file was actually written
                if dest.exists() and dest.stat().st_size > 0:
                    self.logger.info(f"Downloaded {description}: {dest.stat().st_size / (1024 * 1024):.1f} MB")
                    return True
                else:
                    self.logger.warning(f"Download produced empty file: {dest}")

            except urllib.error.HTTPError as e:
                self.logger.error(f"HTTP error downloading {description}: {e.code} {e.reason}")
                self.logger.error(f"URL: {url}")
                if attempt == max_retries:
                    self.logger.error(f"Manual download: curl -L -o '{dest}' '{url}'")
                    return False

            except urllib.error.URLError as e:
                self.logger.error(f"Network error downloading {description}: {e.reason}")
                if attempt == max_retries:
                    self.logger.error("Check your network connection and try again")
                    self.logger.error(f"Manual download: curl -L -o '{dest}' '{url}'")
                    return False

            except Exception as e:
                self.logger.error(f"Unexpected error downloading {description}: {e}")
                if attempt == max_retries:
                    return False

        return False

    # =========================================================================
    # CTI Detection (unified)
    # =========================================================================

    def get_cti_path(self) -> str:
        """Find the CTI file on this system.

        Searches environment variable first, then platform-specific known paths.

        Returns:
            Path to CTI file if found, empty string otherwise
        """
        # 1. Check GENICAM_GENTL64_PATH environment variable
        env_path = os.getenv("GENICAM_GENTL64_PATH", "")
        if env_path:
            for directory in env_path.split(os.pathsep):
                directory = directory.strip()
                if not directory:
                    continue
                for cti_name in ["mvGenTLProducer.cti", "libmvGenTLProducer.cti", "libmvGenTLProducer.so"]:
                    candidate = os.path.join(directory, cti_name)
                    if os.path.exists(candidate):
                        self.logger.debug(f"CTI found via env: {candidate}")
                        return candidate

        # 2. Check GENICAM_CTI_PATH (custom override)
        custom_path = os.getenv("GENICAM_CTI_PATH", "")
        if custom_path and os.path.exists(custom_path):
            self.logger.debug(f"CTI found via GENICAM_CTI_PATH: {custom_path}")
            return custom_path

        # 3. Check platform-specific known paths
        search_paths = self.CTI_SEARCH_PATHS.get(self.platform, [])
        for path in search_paths:
            if os.path.exists(path):
                self.logger.debug(f"CTI found at known path: {path}")
                return path

        return ""

    def verify_cti_installation(self) -> bool:
        """Verify that the CTI file is properly installed.

        Returns:
            True if CTI file exists and is accessible
        """
        cti_path = self.get_cti_path()

        if not cti_path:
            self.logger.error("Matrix Vision GenTL Producer not found")
            self.logger.info("Searched locations:")
            for path in self.CTI_SEARCH_PATHS.get(self.platform, []):
                self.logger.info(f"  - {path}")
            return False

        # Verify file size (CTI files should be > 100KB)
        file_size = os.path.getsize(cti_path)
        if file_size < 100 * 1024:
            self.logger.warning(f"CTI file may be corrupted (only {file_size} bytes): {cti_path}")
            return False

        self.logger.info(f"GenTL Producer found: {cti_path} ({file_size / (1024 * 1024):.1f} MB)")
        return True

    def verify_env_variable(self) -> bool:
        """Verify GENICAM_GENTL64_PATH is set correctly.

        Returns:
            True if environment variable is properly configured
        """
        env_path = os.getenv("GENICAM_GENTL64_PATH", "")

        if not env_path:
            expected = self.GENTL_ENV_PATHS.get(self.platform, "")
            self.logger.error("GENICAM_GENTL64_PATH environment variable not set")
            if expected:
                self.logger.info(f"Expected: export GENICAM_GENTL64_PATH={expected}")
            return False

        self.logger.info(f"GENICAM_GENTL64_PATH is set: {env_path}")
        return True

    def verify_harvesters(self) -> bool:
        """Verify that Harvesters library is available.

        Returns:
            True if Harvesters is importable
        """
        try:
            from harvesters.core import Harvester  # noqa: F401

            self.logger.info("Harvesters library is available")
            return True
        except ImportError:
            self.logger.error("Harvesters library not installed")
            self.logger.info("Install with: pip install harvesters")
            return False

    # =========================================================================
    # Environment Setup
    # =========================================================================

    def _set_env_for_session(self, gentl_dir: str) -> None:
        """Set GENICAM_GENTL64_PATH for the current process.

        Args:
            gentl_dir: Directory containing the GenTL producer
        """
        current = os.getenv("GENICAM_GENTL64_PATH", "")
        if current and gentl_dir in current:
            return

        if current:
            os.environ["GENICAM_GENTL64_PATH"] = f"{gentl_dir}{os.pathsep}{current}"
        else:
            os.environ["GENICAM_GENTL64_PATH"] = gentl_dir

        self.logger.info(f"Set GENICAM_GENTL64_PATH={os.environ['GENICAM_GENTL64_PATH']}")

    def _create_environment_script(self) -> Optional[Path]:
        """Create shell environment setup script.

        Returns:
            Path to created script, or None on Windows
        """
        if self.platform == "Windows":
            return None

        script_path = self.download_dir / "setup_photoneo_env.sh"
        gentl_dir = self.GENTL_ENV_PATHS.get(self.platform, "")

        if not gentl_dir:
            return None

        script_content = f"""#!/bin/bash
# Environment setup for Photoneo 3D scanners (Matrix Vision mvGenTL Producer)
# Generated by mindtrace-scanner-photoneo install
# Source this file: source {script_path}

# Add GenTL producer path
export GENICAM_GENTL64_PATH="{gentl_dir}:${{GENICAM_GENTL64_PATH}}"

echo "Photoneo scanner environment configured:"
echo "  GENICAM_GENTL64_PATH: ${{GENICAM_GENTL64_PATH}}"
"""

        self.download_dir.mkdir(parents=True, exist_ok=True)
        with open(script_path, "w") as f:
            f.write(script_content)

        script_path.chmod(0o755)
        self.logger.info(f"Created environment script: {script_path}")
        return script_path

    def _offer_bashrc_setup(self, script_path: Path) -> None:
        """Offer to add environment setup to ~/.bashrc.

        Args:
            script_path: Path to the environment script
        """
        bashrc_path = Path.home() / ".bashrc"
        source_line = f"source {script_path}"

        # Check if already in bashrc
        if bashrc_path.exists():
            content = bashrc_path.read_text()
            if str(script_path) in content:
                self.logger.info("Environment script already in ~/.bashrc")
                return

        self.logger.info("")
        self.logger.info("To make the environment permanent, add to ~/.bashrc:")
        self.logger.info(f"  echo '{source_line}' >> ~/.bashrc")
        self.logger.info("")
        self.logger.info("Or source it manually in each session:")
        self.logger.info(f"  {source_line}")

    # =========================================================================
    # Discovery
    # =========================================================================

    def discover_devices(self) -> List[dict]:
        """Discover Photoneo devices on the network.

        Returns:
            List of discovered Photoneo devices with their info
        """
        if not self.verify_harvesters():
            return []

        if not self.verify_cti_installation():
            return []

        try:
            from harvesters.core import Harvester

            cti_file = self.get_cti_path()
            if not cti_file:
                self.logger.error("CTI file not found")
                return []

            self.logger.info(f"Using CTI file: {cti_file}")

            h = Harvester()
            h.add_file(cti_file)
            h.update()

            devices = []
            all_devices = []

            self.logger.info(f"Found {len(h.device_info_list)} total GigE Vision devices")

            for dev_info in h.device_info_list:
                vendor = getattr(dev_info, "vendor", "") or ""
                model = getattr(dev_info, "model", "") or ""
                serial = getattr(dev_info, "serial_number", "") or ""
                user_name = getattr(dev_info, "user_defined_name", "") or ""

                all_devices.append(
                    {
                        "vendor": vendor,
                        "model": model,
                        "serial_number": serial,
                        "user_defined_name": user_name,
                    }
                )

                # Check if it's a Photoneo device
                is_photoneo = (
                    "photoneo" in vendor.lower()
                    or "phoxi" in model.lower()
                    or "photoneo" in model.lower()
                    or "motionc" in model.lower()  # MotionCam-3D
                )

                if is_photoneo:
                    devices.append(
                        {
                            "vendor": vendor,
                            "model": model,
                            "serial_number": serial,
                            "user_defined_name": user_name,
                        }
                    )

            # Log all devices for debugging
            if all_devices:
                self.logger.info("All discovered GigE Vision devices:")
                for dev in all_devices:
                    self.logger.info(f"  - {dev['vendor']} {dev['model']} (SN: {dev['serial_number']})")

            h.reset()
            return devices

        except Exception as e:
            self.logger.error(f"Device discovery failed: {e}")
            return []

    # =========================================================================
    # Install
    # =========================================================================

    def install(self) -> bool:
        """Install the Matrix Vision mvGenTL Producer.

        Returns:
            True if installation successful
        """
        self.logger.info(f"Installing Matrix Vision mvGenTL Producer v{self.MVGENTL_VERSION}")
        self.logger.info("This is required for Photoneo scanner communication via GigE Vision")

        if self.platform == "Linux":
            return self._install_linux()
        elif self.platform == "Windows":
            return self._install_windows()
        elif self.platform == "Darwin":
            return self._install_macos()
        else:
            self.logger.error(f"Unsupported platform: {self.platform}")
            self.logger.info("The mvGenTL Producer is available for Linux, Windows, and macOS")
            return False

    def _install_linux(self) -> bool:
        """Install mvGenTL Producer on Linux.

        Returns:
            True if installation successful
        """
        self.logger.info("Installing Matrix Vision mvGenTL Producer for Linux")

        # Download installer and archive
        installer_path = self.download_dir / "install_mvGenTL_Acquire.sh"
        archive_path = self.download_dir / f"mvGenTL_Acquire-x86_64_ABI2-{self.MVGENTL_VERSION}.tgz"

        if not self._download_file(self.LINUX_INSTALLER_URL, installer_path, "installer script"):
            return False

        if not self._download_file(self.LINUX_ARCHIVE_URL, archive_path, "SDK archive"):
            return False

        # Make installer executable
        installer_path.chmod(0o755)

        # Run installer with sudo
        self.logger.info("Running installer (requires sudo)...")
        self.logger.info("NOTE: You may be prompted for your password")

        installer_failed = False
        try:
            self._run_command(
                ["sudo", "bash", str(installer_path)],
                cwd=str(self.download_dir),
            )
        except subprocess.CalledProcessError as e:
            # The installer may return non-zero for optional components (e.g.
            # mvBlueNAOS kernel module) while the GenTL Producer itself installed
            # fine. Don't bail out — fall through to verification.
            self.logger.warning(
                f"Installer exited with code {e.returncode} "
                "(this may be caused by optional components like kernel modules)"
            )
            installer_failed = True
        except FileNotFoundError:
            self.logger.error("sudo not found — cannot install without root privileges")
            return False

        # Set environment for current session
        gentl_dir = self.GENTL_ENV_PATHS.get("Linux", "")
        if gentl_dir:
            self._set_env_for_session(gentl_dir)

        # Source the profile scripts if they exist
        for profile_name in ["genicam.sh", "acquire.sh"]:
            profile_script = Path(f"/etc/profile.d/{profile_name}")
            if profile_script.exists():
                self.logger.info(f"Profile script installed: {profile_script}")

        # Verify installation — the GenTL Producer may have installed even if
        # the overall installer returned non-zero
        if self.verify_cti_installation():
            self.logger.info("Matrix Vision mvGenTL Producer installed successfully")
            if installer_failed:
                self.logger.info(
                    "Note: The installer reported errors for optional components, "
                    "but the GenTL Producer (required for Photoneo) is installed correctly"
                )

            # Create and offer environment script
            env_script = self._create_environment_script()
            if env_script:
                self._offer_bashrc_setup(env_script)

            return True
        else:
            self.logger.error("Installation completed but GenTL Producer verification failed")
            if installer_failed:
                self.logger.info("The installer also reported errors — try running manually:")
                self.logger.info(f"  cd {self.download_dir} && sudo bash {installer_path.name}")
            self.logger.info("Expected CTI file at one of:")
            for path in self.CTI_SEARCH_PATHS.get("Linux", []):
                self.logger.info(f"  - {path}")
            return False

    def _install_windows(self) -> bool:
        """Install mvGenTL Producer on Windows.

        Returns:
            True if installation successful
        """
        self.logger.info("Installing Matrix Vision mvGenTL Producer for Windows")

        # Check for admin privileges
        try:
            import ctypes

            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except (AttributeError, OSError):
            is_admin = False

        if not is_admin:
            self.logger.warning("Administrative privileges may be required for installation")
            self.logger.info("Attempting to elevate privileges...")
            return self._elevate_privileges()

        # Download installer
        installer_path = self.download_dir / f"mvGenTL_Acquire-x86_64-{self.MVGENTL_VERSION}.exe"

        if not self._download_file(self.WINDOWS_INSTALLER_URL, installer_path, "Windows installer"):
            return False

        # Run installer
        self.logger.info("Running installer...")
        self.logger.info("NOTE: Follow the installer prompts")

        try:
            self._run_command([str(installer_path)])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installer failed with exit code {e.returncode}")
            return False

        # Set environment for current session
        gentl_dir = self.GENTL_ENV_PATHS.get("Windows", "")
        if gentl_dir and os.path.isdir(gentl_dir):
            self._set_env_for_session(gentl_dir)

        # Verify installation
        if self.verify_cti_installation():
            self.logger.info("Matrix Vision mvGenTL Producer installed successfully")
            return True
        else:
            self.logger.error("Installation completed but verification failed")
            self.logger.info("Please ensure the installer completed without errors")
            return False

    def _install_macos(self) -> bool:
        """Install mvGenTL Producer on macOS.

        Returns:
            True if installation successful
        """
        self.logger.info("Installing Matrix Vision mvGenTL Producer for macOS")

        # Download DMG
        dmg_path = self.download_dir / f"mvGenTL_Acquire-ARM64_macOS-{self.MVGENTL_VERSION}.dmg"

        if not self._download_file(self.MACOS_DMG_URL, dmg_path, "macOS DMG"):
            return False

        # Mount DMG
        self.logger.info("Mounting DMG file...")
        mount_point = None
        try:
            result = self._run_command(
                ["hdiutil", "attach", str(dmg_path), "-readonly", "-nobrowse"],
                capture_output=True,
                text=True,
            )

            # Extract mount point from hdiutil output
            for line in result.stdout.split("\n"):
                if "/Volumes/" in line:
                    mount_point = line.split("\t")[-1].strip()
                    break

            if not mount_point:
                self.logger.error("Failed to find mount point after mounting DMG")
                self.logger.debug(f"hdiutil output: {result.stdout}")
                return False

            self.logger.info(f"DMG mounted at: {mount_point}")

            # Find and install package
            mount_path = Path(mount_point)
            pkg_files = list(mount_path.glob("*.pkg"))
            app_files = list(mount_path.glob("*.app"))

            if pkg_files:
                pkg_file = pkg_files[0]
                self.logger.info(f"Installing package: {pkg_file.name}")
                self._run_command(["sudo", "installer", "-pkg", str(pkg_file), "-target", "/"])
            elif app_files:
                app_file = app_files[0]
                target_app = Path("/Applications") / app_file.name
                self.logger.info(f"Copying {app_file.name} to /Applications")
                if target_app.exists():
                    shutil.rmtree(target_app)
                shutil.copytree(app_file, target_app)
            else:
                self.logger.error("No .pkg or .app files found in DMG")
                self.logger.info(f"DMG contents: {list(mount_path.iterdir())}")
                return False

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            return False
        except FileNotFoundError:
            self.logger.error("hdiutil not found — is this a macOS system?")
            return False
        finally:
            # Always unmount DMG
            if mount_point:
                self.logger.debug(f"Unmounting: {mount_point}")
                subprocess.run(["hdiutil", "detach", mount_point], check=False, capture_output=True)

        # Set environment for current session
        gentl_dir = self.GENTL_ENV_PATHS.get("Darwin", "")
        if gentl_dir:
            self._set_env_for_session(gentl_dir)

        # Verify installation
        if self.verify_cti_installation():
            self.logger.info("Matrix Vision mvGenTL Producer installed successfully")

            env_script = self._create_environment_script()
            if env_script:
                self._offer_bashrc_setup(env_script)

            return True
        else:
            self.logger.error("Installation completed but verification failed")
            return False

    def _elevate_privileges(self) -> bool:
        """Attempt to elevate privileges on Windows.

        Returns:
            False (elevation requires process restart)
        """
        self.logger.info("Attempting to elevate privileges...")

        try:
            import ctypes

            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join([sys.argv[0]] + sys.argv[1:]), None, 1
            )
            self.logger.info("Elevated process launched — check the new window")
        except Exception as e:
            self.logger.error(f"Failed to elevate: {e}")
            self.logger.error("Please right-click your terminal and select 'Run as administrator'")

        return False

    # =========================================================================
    # Uninstall
    # =========================================================================

    def uninstall(self) -> bool:
        """Uninstall the Matrix Vision mvGenTL Producer.

        Returns:
            True if uninstallation successful
        """
        self.logger.info("Uninstalling Matrix Vision mvGenTL Producer")

        if self.platform == "Linux":
            return self._uninstall_linux()
        elif self.platform == "Windows":
            return self._uninstall_windows()
        elif self.platform == "Darwin":
            return self._uninstall_macos()
        else:
            self.logger.error(f"Unsupported platform: {self.platform}")
            return False

    def _uninstall_linux(self) -> bool:
        """Uninstall on Linux.

        Returns:
            True if successful
        """
        try:
            removed = False

            install_dir = Path("/opt/mvIMPACT_Acquire")
            if install_dir.exists():
                self.logger.info(f"Removing {install_dir}")
                self._run_command(["sudo", "rm", "-rf", str(install_dir)])
                removed = True

            # Also check newer SDK path
            impact_dir = Path("/opt/ImpactAcquire")
            if impact_dir.exists():
                self.logger.info(f"Removing {impact_dir}")
                self._run_command(["sudo", "rm", "-rf", str(impact_dir)])
                removed = True

            # Remove profile script
            profile_script = Path("/etc/profile.d/mvIMPACT_Acquire.sh")
            if profile_script.exists():
                self.logger.info(f"Removing {profile_script}")
                self._run_command(["sudo", "rm", "-f", str(profile_script)])

            # Clean up download directory
            if self.download_dir.exists():
                self.logger.info(f"Removing download cache: {self.download_dir}")
                shutil.rmtree(self.download_dir)

            if removed:
                self.logger.info("Matrix Vision mvGenTL Producer uninstalled")
            else:
                self.logger.info("No installation found to remove")

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            self.logger.info("Try running with sudo manually:")
            self.logger.info("  sudo rm -rf /opt/mvIMPACT_Acquire")
            return False

    def _uninstall_windows(self) -> bool:
        """Uninstall on Windows.

        Returns:
            True if successful
        """
        self.logger.info("Attempting to uninstall Matrix Vision mvGenTL Producer on Windows")

        # Try known uninstaller paths
        uninstaller_paths = [
            r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\uninstall.exe",
            r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\Uninstall.exe",
        ]

        for uninstaller in uninstaller_paths:
            if os.path.exists(uninstaller):
                self.logger.info(f"Found uninstaller: {uninstaller}")
                try:
                    self._run_command([uninstaller])
                    self.logger.info("Uninstaller completed")
                    return True
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Uninstaller returned exit code {e.returncode}")

        # Try via Windows registry (wmic)
        try:
            result = subprocess.run(
                [
                    "wmic",
                    "product",
                    "where",
                    "name like '%mvIMPACT%' or name like '%MATRIX VISION%'",
                    "call",
                    "uninstall",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                self.logger.info("Uninstalled via Windows package manager")
                return True
        except FileNotFoundError:
            pass

        # Fallback: guide user
        self.logger.warning("Could not find automatic uninstaller")
        self.logger.info("Please uninstall manually:")
        self.logger.info("  1. Open Settings > Apps > Installed apps")
        self.logger.info("  2. Search for 'MATRIX VISION' or 'mvIMPACT'")
        self.logger.info("  3. Click Uninstall")

        # Still clean up our download cache
        if self.download_dir.exists():
            shutil.rmtree(self.download_dir)

        return False

    def _uninstall_macos(self) -> bool:
        """Uninstall on macOS.

        Returns:
            True if successful
        """
        try:
            removed = False

            # Remove application
            app_paths = [
                Path("/Applications/mvIMPACT_Acquire.app"),
                Path("/Library/Frameworks/mvGenTLProducer.framework"),
            ]
            for app_path in app_paths:
                if app_path.exists():
                    self.logger.info(f"Removing {app_path}")
                    if app_path.is_dir():
                        shutil.rmtree(app_path)
                    else:
                        app_path.unlink()
                    removed = True

            # Remove other possible install directories
            for dir_path in ["/opt/mvIMPACT_Acquire", "/usr/local/lib/mvIMPACT_Acquire"]:
                if os.path.exists(dir_path):
                    self.logger.info(f"Removing {dir_path}")
                    self._run_command(["sudo", "rm", "-rf", dir_path], check=False)
                    removed = True

            # Clean up download cache
            if self.download_dir.exists():
                shutil.rmtree(self.download_dir)

            if removed:
                self.logger.info("Matrix Vision mvGenTL Producer uninstalled from macOS")
            else:
                self.logger.info("No installation found to remove")

            return True

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    # =========================================================================
    # Verify (aggregate)
    # =========================================================================

    def verify(self) -> bool:
        """Verify complete Photoneo setup.

        Returns:
            True if all components are properly configured
        """
        self.logger.info("Verifying Photoneo/Matrix Vision setup")
        self.logger.info(f"Expected mvGenTL version: {self.MVGENTL_VERSION}")

        all_ok = True

        # Check Harvesters
        if self.verify_harvesters():
            typer.echo("[green]Harvesters library: OK[/green]")
        else:
            typer.echo("[red]Harvesters library: NOT INSTALLED[/red]")
            all_ok = False

        # Check CTI file
        if self.verify_cti_installation():
            typer.echo(f"[green]GenTL Producer: OK ({self.get_cti_path()})[/green]")
        else:
            typer.echo("[red]GenTL Producer: NOT FOUND[/red]")
            all_ok = False

        # Check environment variable
        if self.verify_env_variable():
            typer.echo("[green]GENICAM_GENTL64_PATH: OK[/green]")
        else:
            typer.echo("[yellow]GENICAM_GENTL64_PATH: NOT SET[/yellow]")
            # Don't fail completely, CTI might still work via known paths

        return all_ok


# =========================================================================
# Module-level convenience functions
# =========================================================================


def install_photoneo_sdk() -> bool:
    """Install the SDK required for Photoneo scanners."""
    setup = PhotoneoSetup()
    return setup.install()


def uninstall_photoneo_sdk() -> bool:
    """Uninstall the Photoneo SDK."""
    setup = PhotoneoSetup()
    return setup.uninstall()


def verify_photoneo_sdk() -> bool:
    """Verify Photoneo SDK installation."""
    setup = PhotoneoSetup()
    return setup.verify()


# =========================================================================
# CLI Commands
# =========================================================================


@app.command()
def install(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Install the Matrix Vision mvGenTL Producer for Photoneo scanners.

    Downloads and installs mvGenTL Producer v2.49.0 as recommended by Photoneo.
    See: https://github.com/photoneo-3d/photoneo-python-examples
    """
    setup = PhotoneoSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)

    success = setup.install()
    raise typer.Exit(code=0 if success else 1)


@app.command()
def uninstall(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Uninstall the Matrix Vision mvGenTL Producer."""
    setup = PhotoneoSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)

    success = setup.uninstall()
    raise typer.Exit(code=0 if success else 1)


@app.command()
def verify(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Verify Photoneo SDK installation and configuration."""
    setup = PhotoneoSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)

    success = setup.verify()

    if success:
        typer.echo("\n[green]Photoneo setup verification: PASSED[/green]")
    else:
        typer.echo("\n[red]Photoneo setup verification: FAILED[/red]")
        typer.echo("\nTo install, run: mindtrace-scanner-photoneo install")

    raise typer.Exit(code=0 if success else 1)


@app.command()
def discover(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    all_devices: bool = typer.Option(False, "--all", "-a", help="Show all GigE Vision devices, not just Photoneo"),
) -> None:
    """Discover Photoneo scanners on the network."""
    setup = PhotoneoSetup()

    if verbose:
        setup.logger.setLevel(logging.DEBUG)

    typer.echo("Discovering Photoneo scanners...")

    # Show all GigE devices if --all flag
    if all_devices:
        if not setup.verify_harvesters() or not setup.verify_cti_installation():
            raise typer.Exit(code=1)

        from harvesters.core import Harvester

        cti_file = setup.get_cti_path()
        h = Harvester()
        h.add_file(cti_file)
        h.update()

        typer.echo(f"\n[cyan]All GigE Vision devices ({len(h.device_info_list)} found):[/cyan]")
        for i, dev_info in enumerate(h.device_info_list):
            vendor = getattr(dev_info, "vendor", "") or "N/A"
            model = getattr(dev_info, "model", "") or "N/A"
            serial = getattr(dev_info, "serial_number", "") or "N/A"
            user_name = getattr(dev_info, "user_defined_name", "") or ""
            typer.echo(f"  [{i}] {vendor} / {model}")
            typer.echo(f"      Serial: {serial}")
            if user_name:
                typer.echo(f"      Name: {user_name}")

        h.reset()
        raise typer.Exit(code=0)

    devices = setup.discover_devices()

    if devices:
        typer.echo(f"\n[green]Found {len(devices)} Photoneo scanner(s):[/green]")
        for dev in devices:
            typer.echo(f"  - {dev['vendor']} {dev['model']} (SN: {dev['serial_number']})")
            if dev["user_defined_name"]:
                typer.echo(f"    Name: {dev['user_defined_name']}")
    else:
        typer.echo("\n[yellow]No Photoneo scanners found[/yellow]")
        typer.echo("\nTroubleshooting:")
        typer.echo("  1. Ensure scanner is powered on and connected via Ethernet")
        typer.echo("  2. Check network configuration (same subnet, no firewall blocking)")
        typer.echo("  3. Verify scanner is visible in PhoXi Control")
        typer.echo("  4. Run 'mindtrace-scanner-photoneo verify' to check SDK")
        typer.echo("  5. For older scanners: ensure PhoXi firmware >= 1.13.0")
        typer.echo("\nTip: Run with --all to see all GigE Vision devices")

    raise typer.Exit(code=0 if devices else 1)


def main() -> None:
    """Main entry point for the script."""
    app()


if __name__ == "__main__":
    main()
