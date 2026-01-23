#!/usr/bin/env python3
"""Photoneo 3D Scanner SDK Setup Script

This script automates the setup of the Photoneo 3D scanner environment.
Photoneo scanners use GigE Vision protocol and require the Matrix Vision
mvGenTL Producer for communication via Harvesters.

Based on: https://github.com/photoneo-3d/photoneo-python-examples

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
import urllib.request
from pathlib import Path
from typing import List

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
    # From: https://www.balluff.com/en-de/products/BAL-BVS-SC-MVIMPACT
    MVGENTL_VERSION = "2.49.0"
    MVGENTL_BASE_URL = "https://static.matrix-vision.com/mvIMPACT_Acquire/2.49.0/"

    LINUX_INSTALLER_URL = f"{MVGENTL_BASE_URL}install_mvGenTL_Acquire.sh"
    LINUX_ARCHIVE_URL = f"{MVGENTL_BASE_URL}mvGenTL_Acquire-x86_64_ABI2-{MVGENTL_VERSION}.tgz"
    WINDOWS_INSTALLER_URL = f"{MVGENTL_BASE_URL}mvGenTL_Acquire-x86_64-{MVGENTL_VERSION}.exe"

    # Platform-specific paths
    CTI_PATHS = {
        "Linux": "/opt/mvIMPACT_Acquire/lib/x86_64/mvGenTLProducer.cti",
        "Windows": r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64\mvGenTLProducer.cti",
    }

    GENTL_ENV_PATHS = {
        "Linux": "/opt/mvIMPACT_Acquire/lib/x86_64",
        "Windows": r"C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\x64",
    }

    def __init__(self):
        """Initialize Photoneo setup."""
        super().__init__()
        self.hardware_config = get_hardware_config()
        self.platform = platform.system()
        self.download_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "mvgentl"
        self.logger.info(f"Initializing Photoneo setup for {self.platform}")

    def get_cti_path(self) -> str:
        """Get the expected CTI file path for the current platform.

        Returns:
            Path to the CTI file for the current platform
        """
        # Check environment variable first
        env_path = os.getenv("GENICAM_GENTL64_PATH", "")
        if env_path:
            # Check for CTI file in env path
            for cti_name in ["mvGenTLProducer.cti", "libmvGenTLProducer.cti"]:
                candidate = os.path.join(env_path.split(":")[0], cti_name)
                if os.path.exists(candidate):
                    return candidate

        return self.CTI_PATHS.get(self.platform, "")

    def verify_cti_installation(self) -> bool:
        """Verify that the CTI file is properly installed.

        Returns:
            True if CTI file exists and is accessible, False otherwise
        """
        cti_path = self.get_cti_path()

        # Also check the .so file on Linux
        if self.platform == "Linux":
            so_path = "/opt/mvIMPACT_Acquire/lib/x86_64/libmvGenTLProducer.so"
            if os.path.exists(so_path):
                self.logger.info(f"GenTL Producer found: {so_path}")
                return True

        if cti_path and os.path.exists(cti_path):
            self.logger.info(f"CTI file found: {cti_path}")
            return True

        self.logger.error("Matrix Vision GenTL Producer not found")
        return False

    def verify_env_variable(self) -> bool:
        """Verify GENICAM_GENTL64_PATH is set correctly.

        Returns:
            True if environment variable is properly configured
        """
        env_path = os.getenv("GENICAM_GENTL64_PATH", "")
        expected_path = self.GENTL_ENV_PATHS.get(self.platform, "")

        if not env_path:
            self.logger.error("GENICAM_GENTL64_PATH environment variable not set")
            self.logger.info(f"Expected: export GENICAM_GENTL64_PATH={expected_path}")
            return False

        if expected_path and expected_path not in env_path:
            self.logger.warning("GENICAM_GENTL64_PATH may not include expected path")
            self.logger.info(f"Current: {env_path}")
            self.logger.info(f"Expected to contain: {expected_path}")

        self.logger.info(f"GENICAM_GENTL64_PATH is set: {env_path}")
        return True

    def verify_harvesters(self) -> bool:
        """Verify that Harvesters library is available.

        Returns:
            True if Harvesters is importable, False otherwise
        """
        try:
            from harvesters.core import Harvester  # noqa: F401

            self.logger.info("Harvesters library is available")
            return True
        except ImportError:
            self.logger.error("Harvesters library not installed")
            self.logger.info("Install with: pip install harvesters")
            return False

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

            # Get CTI path from environment or default
            env_path = os.getenv("GENICAM_GENTL64_PATH", "")
            cti_file = None

            if env_path:
                for path in env_path.split(":"):
                    for cti_name in ["mvGenTLProducer.cti", "libmvGenTLProducer.cti"]:
                        candidate = os.path.join(path, cti_name)
                        if os.path.exists(candidate):
                            cti_file = candidate
                            break
                    if cti_file:
                        break

            if not cti_file:
                cti_file = self.get_cti_path()

            if not cti_file or not os.path.exists(cti_file):
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

    def install(self) -> bool:
        """Install the Matrix Vision mvGenTL Producer.

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info(f"Installing Matrix Vision mvGenTL Producer v{self.MVGENTL_VERSION}")
        self.logger.info("This is required for Photoneo scanner communication via GigE Vision")

        if self.platform == "Linux":
            return self._install_linux()
        elif self.platform == "Windows":
            return self._install_windows()
        else:
            self.logger.error(f"Unsupported platform: {self.platform}")
            return False

    def _install_linux(self) -> bool:
        """Install mvGenTL Producer on Linux.

        Returns:
            True if installation successful
        """
        self.logger.info("Installing Matrix Vision mvGenTL Producer for Linux")

        try:
            # Create download directory
            self.download_dir.mkdir(parents=True, exist_ok=True)

            # Download installer script
            installer_path = self.download_dir / "install_mvGenTL_Acquire.sh"
            archive_path = self.download_dir / f"mvGenTL_Acquire-x86_64_ABI2-{self.MVGENTL_VERSION}.tgz"

            self.logger.info(f"Downloading installer from {self.LINUX_INSTALLER_URL}")
            urllib.request.urlretrieve(self.LINUX_INSTALLER_URL, installer_path)

            self.logger.info(f"Downloading archive from {self.LINUX_ARCHIVE_URL}")
            urllib.request.urlretrieve(self.LINUX_ARCHIVE_URL, archive_path)

            # Make installer executable
            os.chmod(installer_path, 0o755)

            # Run installer with sudo
            self.logger.info("Running installer (requires sudo)...")
            self.logger.info("NOTE: You may be prompted for your password")

            # The installer needs both files in the same directory
            result = subprocess.run(
                ["sudo", "bash", str(installer_path)],
                cwd=str(self.download_dir),
                check=False,
            )

            if result.returncode != 0:
                self.logger.error("Installation failed")
                return False

            # Verify installation
            if self.verify_cti_installation():
                self.logger.info("Matrix Vision mvGenTL Producer installed successfully")
                self.logger.info("")
                self.logger.info("IMPORTANT: Please log out and log back in for environment changes to take effect")
                self.logger.info("Or run: source /etc/profile.d/mvIMPACT_Acquire.sh")
                return True
            else:
                self.logger.error("Installation completed but verification failed")
                return False

        except Exception as e:
            self.logger.error(f"Installation failed: {e}")
            return False

    def _install_windows(self) -> bool:
        """Install mvGenTL Producer on Windows.

        Returns:
            True if installation successful
        """
        self.logger.info("Installing Matrix Vision mvGenTL Producer for Windows")

        try:
            # Create download directory
            self.download_dir.mkdir(parents=True, exist_ok=True)

            # Download installer
            installer_path = self.download_dir / f"mvGenTL_Acquire-x86_64-{self.MVGENTL_VERSION}.exe"

            self.logger.info(f"Downloading installer from {self.WINDOWS_INSTALLER_URL}")
            urllib.request.urlretrieve(self.WINDOWS_INSTALLER_URL, installer_path)

            # Run installer
            self.logger.info("Running installer...")
            self.logger.info("NOTE: Follow the installer prompts")

            subprocess.run([str(installer_path)], check=True)

            # Verify installation
            if self.verify_cti_installation():
                self.logger.info("Matrix Vision mvGenTL Producer installed successfully")
                self.logger.info("")
                self.logger.info("IMPORTANT: Disable GigE Vision NDIS 6.x Filter Driver")
                self.logger.info("Also configure firewall to allow UDP from device IP")
                return True
            else:
                self.logger.error("Installation completed but verification failed")
                return False

        except Exception as e:
            self.logger.error(f"Installation failed: {e}")
            return False

    def uninstall(self) -> bool:
        """Uninstall the Matrix Vision mvGenTL Producer.

        Returns:
            True if uninstallation successful
        """
        self.logger.info("Uninstalling Matrix Vision mvGenTL Producer")

        if self.platform == "Linux":
            return self._uninstall_linux()
        elif self.platform == "Windows":
            self.logger.warning("Please uninstall via Windows Control Panel")
            return False
        else:
            self.logger.error(f"Unsupported platform: {self.platform}")
            return False

    def _uninstall_linux(self) -> bool:
        """Uninstall on Linux.

        Returns:
            True if successful
        """
        try:
            install_dir = Path("/opt/mvIMPACT_Acquire")
            if install_dir.exists():
                self.logger.info(f"Removing {install_dir}")
                subprocess.run(["sudo", "rm", "-rf", str(install_dir)], check=True)

            # Clean up download directory
            if self.download_dir.exists():
                shutil.rmtree(self.download_dir)

            self.logger.info("Matrix Vision mvGenTL Producer uninstalled")
            return True

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

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
            typer.echo("[green]GenTL Producer: OK[/green]")
        else:
            typer.echo("[red]GenTL Producer: NOT FOUND[/red]")
            all_ok = False

        # Check environment variable
        if self.verify_env_variable():
            typer.echo("[green]GENICAM_GENTL64_PATH: OK[/green]")
        else:
            typer.echo("[yellow]GENICAM_GENTL64_PATH: NOT SET[/yellow]")
            # Don't fail completely, CTI might still work

        return all_ok


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

    # Get all devices for debugging if --all flag is set
    if all_devices:
        if not setup.verify_harvesters() or not setup.verify_cti_installation():
            raise typer.Exit(code=1)

        import os

        from harvesters.core import Harvester

        env_path = os.getenv("GENICAM_GENTL64_PATH", "")
        cti_file = None
        if env_path:
            for path in env_path.split(":"):
                for cti_name in ["mvGenTLProducer.cti", "libmvGenTLProducer.cti"]:
                    candidate = os.path.join(path, cti_name)
                    if os.path.exists(candidate):
                        cti_file = candidate
                        break
                if cti_file:
                    break

        if not cti_file:
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
