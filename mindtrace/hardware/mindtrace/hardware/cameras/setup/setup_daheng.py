#!/usr/bin/env python3
"""Daheng Galaxy SDK Setup Script

This script provides a guided installation wizard for the Daheng Galaxy SDK
for both Linux and Windows systems. The Galaxy SDK provides the native libraries
required by gxipy (the Python package) as well as GUI tools like Galaxy Viewer.

Note: Unlike pypylon, gxipy is NOT self-contained - the Galaxy SDK native
libraries (libgxiapi.so on Linux, GxIAPI.dll on Windows) must be installed
for gxipy to function.

Features:
- Interactive guided wizard with browser integration
- Platform-specific installation instructions
- Support for pre-downloaded packages (--package flag)
- Galaxy SDK native library verification
- CTI file detection (GxGVTL.cti, GxU3VTL.cti for GenICam/Harvesters)
- Comprehensive logging and error handling
- Uninstallation support

Usage:
    python setup_daheng.py                      # Interactive wizard
    python setup_daheng.py --package /path/to/file  # Use pre-downloaded file
    python setup_daheng.py --uninstall          # Uninstall SDK
    python setup_daheng.py --verify             # Verify installation
    mindtrace-camera-daheng                     # Console script
"""

import ctypes
import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import List, Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.config import get_hardware_config

# Typer app instance
app = typer.Typer(
    name="daheng-setup",
    help="Install or uninstall the Daheng Galaxy SDK (guided wizard)",
    add_completion=False,
    rich_markup_mode="rich",
)


class GalaxySDKInstaller(Mindtrace):
    """Daheng Galaxy SDK installer with guided wizard.

    This class provides an interactive installation wizard that guides users
    through downloading and installing the Daheng Galaxy SDK from the official
    Daheng Imaging website.
    """

    # Daheng official download page
    DAHENG_DOWNLOAD_PAGE = "https://en.daheng-imaging.com/list-59-1.html"

    # Platform-specific download instructions
    PLATFORM_INFO = {
        "Linux": {
            "search_term": "Galaxy Linux x86 GigE & USB3 Vision",
            "file_pattern": "Galaxy_Linux*.run",
            "file_description": "Galaxy_Linux-x86_Gige-U3_*.run (or .tar.gz)",
            "min_size_mb": 25,
        },
        "Windows": {
            "search_term": "Galaxy Windows SDK",
            "file_pattern": "Galaxy_Windows*.exe",
            "file_description": "Galaxy_Windows_*.exe",
            "min_size_mb": 100,
        },
    }

    # Platform-specific native library paths to verify
    NATIVE_LIB_PATHS = {
        "Linux": [
            "/usr/lib/libgxiapi.so",
            "/usr/lib/x86_64-linux-gnu/libgxiapi.so",
            "/usr/local/lib/libgxiapi.so",
        ],
        "Windows": [
            r"C:\Program Files\Daheng Imaging\GalaxySDK\APIDll\Win64\GxIAPI.dll",
            r"C:\Program Files (x86)\Daheng Imaging\GalaxySDK\APIDll\Win32\GxIAPI.dll",
        ],
    }

    # CTI file locations (bonus: enables GenICam/Harvesters path)
    CTI_PATHS = {
        "Linux": [
            "/usr/lib/GxGVTL.cti",
            "/usr/lib/GxU3VTL.cti",
            "/usr/lib/x86_64-linux-gnu/GxGVTL.cti",
        ],
        "Windows": [
            r"C:\Program Files\Daheng Imaging\GalaxySDK\APIDll\Win64\GxGVTL.cti",
            r"C:\Program Files\Daheng Imaging\GalaxySDK\APIDll\Win64\GxU3VTL.cti",
        ],
    }

    # Linux dependencies
    LINUX_DEPENDENCIES = ["libusb-1.0-0", "libusb-1.0-0-dev"]

    def __init__(self, package_path: Optional[str] = None):
        """Initialize the Galaxy SDK installer.

        Args:
            package_path: Optional path to pre-downloaded package file
        """
        super().__init__()

        self.hardware_config = get_hardware_config()
        self.galaxy_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "galaxy_sdk"
        self.platform = platform.system()
        self.package_path = Path(package_path) if package_path else None

        self.logger.info(f"Initializing Galaxy SDK installer for {self.platform}")
        self.logger.debug(f"Installation directory: {self.galaxy_dir}")

    def install(self) -> bool:
        """Install the Galaxy SDK using interactive wizard or pre-downloaded package.

        Returns:
            True if installation successful, False otherwise
        """
        if self.platform not in self.PLATFORM_INFO:
            rprint(f"[red]Unsupported platform: {self.platform}[/]")
            rprint("The Galaxy SDK is available for Linux and Windows.")
            return False

        if self.package_path:
            return self._install_from_package(self.package_path)

        return self._run_wizard()

    def _run_wizard(self) -> bool:
        """Run the interactive installation wizard.

        Returns:
            True if installation successful, False otherwise
        """
        platform_info = self.PLATFORM_INFO[self.platform]

        self._display_intro()

        if not typer.confirm("\nProceed with installation?", default=True):
            rprint("[yellow]Installation cancelled.[/]")
            return False

        self._open_download_page()
        self._show_download_instructions(platform_info)

        rprint("\n[bold cyan]Step 3/5:[/] Download the SDK")
        rprint("         Please download the file from the opened browser page.")
        rprint("         You may need to create an account and accept the EULA.\n")

        input("         Press Enter when download is complete...")

        package_path = self._prompt_for_file(platform_info)
        if not package_path:
            return False

        return self._install_from_package(package_path)

    def _display_intro(self) -> None:
        """Display introductory information panel."""
        intro_text = """[bold]Daheng Galaxy SDK Installation Wizard[/]

This wizard will help you install the Daheng Galaxy SDK which provides:

  [cyan]Native Libraries[/]    - Required for gxipy Python package to function
  [cyan]Galaxy Viewer[/]       - GUI for live camera view and configuration
  [cyan]GenTL Producers[/]     - CTI files for GenICam/Harvesters compatibility

[dim]Unlike Basler's pypylon, the gxipy Python package requires the Galaxy SDK
native libraries to be installed separately on the system.[/]

You will be guided to download the SDK from Daheng's official website
where you may need to create an account and accept their EULA."""

        rprint(Panel(intro_text, title="Galaxy SDK Setup", border_style="blue"))

    def _open_download_page(self) -> None:
        """Open Daheng download page in default browser."""
        import webbrowser

        rprint("\n[bold cyan]Step 1/5:[/] Opening Daheng download page...")

        try:
            webbrowser.open(self.DAHENG_DOWNLOAD_PAGE)
            rprint(f"         Browser opened to: [link={self.DAHENG_DOWNLOAD_PAGE}]{self.DAHENG_DOWNLOAD_PAGE}[/]")
        except Exception as e:
            rprint(f"[yellow]         Could not open browser automatically: {e}[/]")
            rprint(f"         Please open manually: {self.DAHENG_DOWNLOAD_PAGE}")

    def _show_download_instructions(self, platform_info: dict) -> None:
        """Show platform-specific download instructions."""
        rprint("\n[bold cyan]Step 2/5:[/] Find the correct download")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="dim")
        table.add_column("Value")

        table.add_row("Platform:", f"[green]{self.platform}[/]")
        table.add_row("Search for:", f"[cyan]{platform_info['search_term']}[/]")
        table.add_row("File name:", f"[cyan]{platform_info['file_description']}[/]")
        table.add_row("Expected size:", f">{platform_info['min_size_mb']} MB")

        rprint(table)

    def _prompt_for_file(self, platform_info: dict) -> Optional[Path]:
        """Prompt user for downloaded file path.

        Args:
            platform_info: Platform-specific information dict

        Returns:
            Path to the downloaded file, or None if invalid/cancelled
        """
        rprint("\n[bold cyan]Step 4/5:[/] Locate the downloaded file")

        while True:
            path_str = typer.prompt("         Enter path to downloaded file (or 'q' to quit)")

            if path_str.lower() == "q":
                rprint("[yellow]Installation cancelled.[/]")
                return None

            path_str = path_str.strip().strip("'\"").replace("\\ ", " ")
            path = Path(path_str).expanduser()

            if not path.exists():
                rprint(f"[red]         File not found: {path}[/]")
                continue

            if not self._validate_package(path, platform_info):
                if not typer.confirm("         Use this file anyway?", default=False):
                    continue

            rprint(f"[green]         File accepted: {path.name}[/]")
            return path

    def _validate_package(self, path: Path, platform_info: dict) -> bool:
        """Validate the downloaded package file."""
        size_mb = path.stat().st_size / (1024 * 1024)
        min_size = platform_info["min_size_mb"]

        if size_mb < min_size:
            rprint(
                f"[yellow]         Warning: File size ({size_mb:.1f} MB) is smaller than expected (>{min_size} MB)[/]"
            )
            return False

        name = path.name.lower()
        if "galaxy" not in name and "gxiapi" not in name:
            rprint("[yellow]         Warning: File name doesn't appear to be a Galaxy SDK package[/]")
            return False

        rprint(f"         File size: {size_mb:.1f} MB")
        return True

    def _install_from_package(self, package_path: Path) -> bool:
        """Install from a local package file.

        Args:
            package_path: Path to the package file

        Returns:
            True if installation successful, False otherwise
        """
        rprint("\n[bold cyan]Step 5/5:[/] Installing...")

        try:
            if self.platform == "Linux":
                return self._install_linux(package_path)
            elif self.platform == "Windows":
                return self._install_windows(package_path)
            else:
                rprint(f"[red]Unsupported platform: {self.platform}[/]")
                return False

        except Exception as e:
            self.logger.error(f"Installation failed: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            return False

    def _install_linux(self, package_path: Path) -> bool:
        """Install Galaxy SDK on Linux.

        Args:
            package_path: Path to the downloaded package

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Galaxy SDK for Linux")

        try:
            # Install dependencies
            rprint("         Installing system dependencies...")
            self._run_command(["sudo", "apt-get", "update"])
            self._run_command(["sudo", "apt-get", "install", "-y"] + self.LINUX_DEPENDENCIES)

            # Handle .run installer
            if package_path.suffix == ".run":
                rprint("         Making installer executable...")
                self._run_command(["chmod", "+x", str(package_path)])

                rprint("         Running Galaxy SDK installer...")
                rprint("         [dim]Follow the on-screen prompts (press Enter, then type 'Y').[/]")
                subprocess.run(["sudo", str(package_path)], check=True)

            elif ".tar" in package_path.name:
                import tarfile

                self.galaxy_dir.mkdir(parents=True, exist_ok=True)
                rprint("         Extracting package...")

                with tarfile.open(package_path) as tar:
                    tar.extractall(path=self.galaxy_dir)

                # Look for .run installer in extracted contents
                run_files = list(self.galaxy_dir.rglob("*.run"))
                if run_files:
                    run_file = run_files[0]
                    self._run_command(["chmod", "+x", str(run_file)])
                    rprint("         Running extracted installer...")
                    subprocess.run(["sudo", str(run_file)], check=True)
                else:
                    rprint("[yellow]         No .run installer found in archive. Manual installation may be needed.[/]")
            else:
                rprint(f"[red]Unsupported package format: {package_path.suffix}[/]")
                return False

            # Verify installation
            if self.verify_installation():
                self._show_success_message()
                return True
            else:
                rprint("[yellow]Installation completed but verification found issues. See details above.[/]")
                return False

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            rprint(f"[red]Package installation failed: {e}[/]")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            return False

    def _install_windows(self, package_path: Path) -> bool:
        """Install Galaxy SDK on Windows.

        Args:
            package_path: Path to the downloaded package

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Galaxy SDK for Windows")

        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            is_admin = False

        if not is_admin:
            rprint("[yellow]Administrative privileges may be required.[/]")
            rprint("If installation fails, please run as Administrator.")

        try:
            rprint("         Running installer...")
            rprint("         [dim]Follow the on-screen prompts to complete installation.[/]")

            if package_path.suffix == ".exe":
                subprocess.run([str(package_path)], check=True)
            else:
                rprint(f"[red]Unsupported package format: {package_path.suffix}[/]")
                return False

            if self.verify_installation():
                self._show_success_message()
                return True
            else:
                rprint("[yellow]Installation completed but verification found issues.[/]")
                return False

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            return False

    def verify_installation(self) -> bool:
        """Verify that the Galaxy SDK is properly installed.

        Returns:
            True if native libraries are found, False otherwise
        """
        self.logger.info("Verifying Galaxy SDK installation")

        native_found = False
        cti_found = False

        # Check native libraries
        native_paths = self.NATIVE_LIB_PATHS.get(self.platform, [])
        for lib_path in native_paths:
            if os.path.exists(lib_path):
                self.logger.info(f"  Native library found: {lib_path}")
                rprint(f"[green]         Native library found: {lib_path}[/]")
                native_found = True
                break

        if not native_found:
            self.logger.warning("  Native library not found in standard paths")
            rprint("[yellow]         Native library not found in standard paths[/]")

        # Check CTI files
        cti_paths = self.CTI_PATHS.get(self.platform, [])
        for cti_path in cti_paths:
            if os.path.exists(cti_path):
                self.logger.info(f"  CTI file found: {cti_path}")
                rprint(f"[green]         CTI file found: {cti_path}[/]")
                cti_found = True

        if not cti_found:
            self.logger.info("  CTI files not found (GenICam/Harvesters support unavailable)")
            rprint("[dim]         CTI files not found (GenICam/Harvesters compatibility unavailable)[/]")

        # Check gxipy Python package
        try:
            import gxipy  # noqa: F401

            self.logger.info("  gxipy Python package: available")
            rprint("[green]         gxipy Python package: available[/]")
        except ImportError:
            self.logger.info("  gxipy Python package: not installed (pip install iai-gxipy)")
            rprint("[yellow]         gxipy Python package: not installed (pip install iai-gxipy)[/]")

        return native_found

    def _show_success_message(self) -> None:
        """Display installation success message."""
        success_text = """[bold green]Installation Complete![/]

[bold]Installed Components:[/]
  Galaxy SDK        - Native libraries for camera communication
  Galaxy Viewer     - GUI for live camera view and configuration

[bold]Next Steps:[/]"""

        if self.platform == "Linux":
            success_text += """
  1. Install Python bindings: [cyan]pip install iai-gxipy[/]
  2. Log out and log back in for library path changes to take effect
  3. Connect your Daheng camera AFTER installation
  4. Verify with: [cyan]python -c "import gxipy as gx; print(gx.DeviceManager().update_device_list())"[/]"""
        else:
            success_text += """
  1. Install Python bindings: [cyan]pip install iai-gxipy[/]
  2. Restart any applications that need to access cameras
  3. Galaxy Viewer is available in the Start Menu"""

        rprint(Panel(success_text, border_style="green"))

    def _run_command(self, cmd: List[str]) -> None:
        """Run a system command with logging."""
        self.logger.debug(f"Running command: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

    def uninstall(self) -> bool:
        """Uninstall the Galaxy SDK.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Starting Galaxy SDK uninstallation")

        try:
            if self.platform == "Linux":
                return self._uninstall_linux()
            elif self.platform == "Windows":
                return self._uninstall_windows()
            else:
                rprint(f"[red]Unsupported platform: {self.platform}[/]")
                return False
        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            rprint(f"[red]Uninstallation failed: {e}[/]")
            return False

    def _uninstall_linux(self) -> bool:
        """Uninstall Galaxy SDK on Linux."""
        rprint("Uninstalling Galaxy SDK from Linux...")

        try:
            # Look for uninstall script
            uninstall_paths = [
                "/opt/Galaxy_camera/uninstall.sh",
                "/usr/local/Galaxy_camera/uninstall.sh",
            ]

            for uninstall_path in uninstall_paths:
                if os.path.exists(uninstall_path):
                    rprint(f"Running uninstaller: {uninstall_path}")
                    subprocess.run(["sudo", "bash", uninstall_path], check=False)
                    rprint("[green]Galaxy SDK uninstalled successfully.[/]")
                    return True

            # Manual cleanup
            rprint("No uninstall script found, performing manual cleanup...")
            cleanup_paths = ["/opt/Galaxy_camera", "/usr/lib/libgxiapi.so"]
            for path in cleanup_paths:
                if os.path.exists(path):
                    subprocess.run(["sudo", "rm", "-rf", path], check=False)

            rprint("[green]Galaxy SDK files removed.[/]")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    def _uninstall_windows(self) -> bool:
        """Uninstall Galaxy SDK on Windows."""
        rprint("[yellow]Automatic uninstallation on Windows is not supported.[/]")
        rprint("Please use Windows Settings > Apps to uninstall the Galaxy SDK.")
        return False


def install_daheng_sdk() -> bool:
    """Install the Daheng Galaxy SDK.

    Returns:
        True if installation successful, False otherwise
    """
    installer = GalaxySDKInstaller()
    return installer.install()


def uninstall_daheng_sdk() -> bool:
    """Uninstall the Daheng Galaxy SDK.

    Returns:
        True if uninstallation successful, False otherwise
    """
    installer = GalaxySDKInstaller()
    return installer.uninstall()


def verify_daheng_sdk() -> bool:
    """Verify the Daheng Galaxy SDK installation.

    Returns:
        True if SDK is properly installed, False otherwise
    """
    installer = GalaxySDKInstaller()
    return installer.verify_installation()


@app.command()
def install(
    package: Optional[Path] = typer.Option(
        None,
        "--package",
        "-p",
        help="Path to pre-downloaded Galaxy SDK package file",
        exists=True,
        dir_okay=False,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Install the Daheng Galaxy SDK using an interactive wizard.

    The wizard will guide you through downloading and installing the SDK
    from Daheng's official website where you may need to accept their EULA.

    For CI/automation, use --package to provide a pre-downloaded file.
    """
    installer = GalaxySDKInstaller(package_path=str(package) if package else None)

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
    """Uninstall the Daheng Galaxy SDK."""
    installer = GalaxySDKInstaller()

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.uninstall()
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
    """Verify that the Galaxy SDK is properly installed."""
    installer = GalaxySDKInstaller()

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.verify_installation()

    if success:
        typer.echo("Galaxy SDK verification successful")
    else:
        typer.echo("Galaxy SDK verification failed", err=True)

    raise typer.Exit(code=0 if success else 1)


def main() -> None:
    """Main entry point for the script."""
    app()


if __name__ == "__main__":
    main()
