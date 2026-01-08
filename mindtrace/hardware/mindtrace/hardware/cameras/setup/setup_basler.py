#!/usr/bin/env python3
"""Basler Pylon SDK Setup Script

This script provides a guided installation wizard for the Basler Pylon SDK
for both Linux and Windows systems. The Pylon SDK provides tools like
Pylon Viewer and IP Configurator for camera management.

Note: pypylon (the Python package) is self-contained for camera operations.
This SDK installation is only needed for the GUI tools.

Features:
- Interactive guided wizard with browser integration
- Platform-specific installation instructions
- Support for pre-downloaded packages (--package flag)
- Comprehensive logging and error handling
- Uninstallation support

Usage:
    python setup_basler.py                      # Interactive wizard
    python setup_basler.py --package /path/to/file  # Use pre-downloaded file
    python setup_basler.py --uninstall          # Uninstall SDK
    mindtrace-camera-basler-install            # Console script (install)
    mindtrace-camera-basler-uninstall          # Console script (uninstall)
"""

import ctypes
import logging
import os
import platform
import subprocess
import webbrowser
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
    name="pylon-setup",
    help="Install or uninstall the Basler Pylon SDK (guided wizard)",
    add_completion=False,
    rich_markup_mode="rich",
)


class PylonSDKInstaller(Mindtrace):
    """Basler Pylon SDK installer with guided wizard.

    This class provides an interactive installation wizard that guides users
    through downloading and installing the Basler Pylon SDK from the official
    Basler website.
    """

    # Basler official download page
    BASLER_DOWNLOAD_PAGE = "https://www.baslerweb.com/en/downloads/software-downloads/"

    # Platform-specific download instructions
    PLATFORM_INFO = {
        "Linux": {
            "search_term": "pylon Camera Software Suite Linux x86 (64 Bit)",
            "file_pattern": "pylon*linux*x86_64*.tar.gz",
            "file_description": "pylon_X.X.X_linux-x86_64_debs.tar.gz",
            "min_size_mb": 100,
        },
        "Windows": {
            "search_term": "pylon Camera Software Suite Windows",
            "file_pattern": "Basler*pylon*.exe",
            "file_description": "Basler_pylon_X.X.X.exe",
            "min_size_mb": 200,
        },
    }

    # Linux dependencies required for Pylon SDK
    LINUX_DEPENDENCIES = ["libglx-mesa0", "libgl1", "libxcb-xinerama0", "libxcb-xinput0", "libxcb-cursor0"]

    def __init__(self, package_path: Optional[str] = None):
        """Initialize the Pylon SDK installer.

        Args:
            package_path: Optional path to pre-downloaded package file
        """
        super().__init__()

        self.hardware_config = get_hardware_config()
        self.pylon_dir = Path(self.hardware_config.get_config().paths.lib_dir).expanduser() / "pylon"
        self.platform = platform.system()
        self.package_path = Path(package_path) if package_path else None

        self.logger.info(f"Initializing Pylon SDK installer for {self.platform}")
        self.logger.debug(f"Installation directory: {self.pylon_dir}")

    def install(self) -> bool:
        """Install the Pylon SDK using interactive wizard or pre-downloaded package.

        Returns:
            True if installation successful, False otherwise
        """
        if self.platform not in self.PLATFORM_INFO:
            rprint(f"[red]Unsupported platform: {self.platform}[/]")
            rprint("The Pylon SDK is only available for Linux and Windows.")
            return False

        # If package path provided, skip wizard and install directly
        if self.package_path:
            return self._install_from_package(self.package_path)

        # Run interactive wizard
        return self._run_wizard()

    def _run_wizard(self) -> bool:
        """Run the interactive installation wizard.

        Returns:
            True if installation successful, False otherwise
        """
        platform_info = self.PLATFORM_INFO[self.platform]

        # Step 1: Display info panel
        self._display_intro()

        # Step 2: Confirm user wants to proceed
        if not typer.confirm("\nProceed with installation?", default=True):
            rprint("[yellow]Installation cancelled.[/]")
            return False

        # Step 3: Open browser
        self._open_download_page()

        # Step 4: Show download instructions
        self._show_download_instructions(platform_info)

        # Step 5: Wait for user to download
        rprint("\n[bold cyan]Step 3/5:[/] Download the SDK")
        rprint("         Please download the file from the opened browser page.")
        rprint("         Accept the EULA when prompted.\n")

        input("         Press Enter when download is complete...")

        # Step 6: Get file path from user
        package_path = self._prompt_for_file(platform_info)
        if not package_path:
            return False

        # Step 7: Install
        return self._install_from_package(package_path)

    def _display_intro(self) -> None:
        """Display introductory information panel."""
        intro_text = """[bold]Basler Pylon SDK Installation Wizard[/]

This wizard will help you install the Basler Pylon SDK which provides:

  [cyan]Pylon Viewer[/]      - GUI for live camera view and configuration
  [cyan]IP Configurator[/]   - Tool to set GigE camera IP addresses

[dim]Note: The pypylon Python package is self-contained for camera operations.
This SDK installation is only needed for the GUI tools.[/]

You will be guided to download the SDK from Basler's official website
where you'll need to accept their End User License Agreement (EULA)."""

        rprint(Panel(intro_text, title="Pylon SDK Setup", border_style="blue"))

    def _open_download_page(self) -> None:
        """Open Basler download page in default browser."""
        rprint("\n[bold cyan]Step 1/5:[/] Opening Basler download page...")

        try:
            webbrowser.open(self.BASLER_DOWNLOAD_PAGE)
            rprint(f"         Browser opened to: [link={self.BASLER_DOWNLOAD_PAGE}]{self.BASLER_DOWNLOAD_PAGE}[/]")
        except Exception as e:
            rprint(f"[yellow]         Could not open browser automatically: {e}[/]")
            rprint(f"         Please open manually: {self.BASLER_DOWNLOAD_PAGE}")

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

            # Handle drag & drop (removes quotes, escapes)
            path_str = path_str.strip().strip("'\"").replace("\\ ", " ")

            path = Path(path_str).expanduser()

            if not path.exists():
                rprint(f"[red]         File not found: {path}[/]")
                continue

            # Validate file
            if not self._validate_package(path, platform_info):
                if not typer.confirm("         Use this file anyway?", default=False):
                    continue

            rprint(f"[green]         File accepted: {path.name}[/]")
            return path

    def _validate_package(self, path: Path, platform_info: dict) -> bool:
        """Validate the downloaded package file.

        Args:
            path: Path to the package file
            platform_info: Platform-specific information dict

        Returns:
            True if file appears valid, False otherwise
        """
        # Check file size
        size_mb = path.stat().st_size / (1024 * 1024)
        min_size = platform_info["min_size_mb"]

        if size_mb < min_size:
            rprint(
                f"[yellow]         Warning: File size ({size_mb:.1f} MB) is smaller than expected (>{min_size} MB)[/]"
            )
            return False

        # Check file name pattern
        name = path.name.lower()
        if "pylon" not in name:
            rprint("[yellow]         Warning: File name doesn't contain 'pylon'[/]")
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
        """Install Pylon SDK on Linux from local package.

        Args:
            package_path: Path to the downloaded package

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Pylon SDK for Linux")

        try:
            # Create extraction directory
            self.pylon_dir.mkdir(parents=True, exist_ok=True)

            # Extract the package
            rprint("         Extracting package...")

            if package_path.suffix == ".gz" or ".tar" in package_path.name:
                import tarfile

                with tarfile.open(package_path, "r:gz") as tar:
                    tar.extractall(path=self.pylon_dir)
            else:
                rprint(f"[red]Unsupported package format: {package_path.suffix}[/]")
                return False

            # Find extracted directory
            extracted_items = list(self.pylon_dir.iterdir())
            self.logger.debug(f"Extracted items: {extracted_items}")

            # Change to extracted directory to find .deb files
            original_cwd = os.getcwd()

            # Look for .deb files in extraction
            deb_files = list(self.pylon_dir.rglob("*.deb"))

            if deb_files:
                # Install dependencies first
                rprint("         Installing system dependencies...")
                self._run_command(["sudo", "apt-get", "update"])
                self._run_command(["sudo", "apt-get", "install", "-y"] + self.LINUX_DEPENDENCIES)

                # Install all .deb packages
                rprint(f"         Installing {len(deb_files)} packages...")
                for deb in deb_files:
                    self.logger.info(f"Installing {deb.name}")
                    self._run_command(["sudo", "dpkg", "-i", str(deb)])

                # Fix any missing dependencies
                self._run_command(["sudo", "apt-get", "-f", "install", "-y"])

            os.chdir(original_cwd)

            self._show_success_message()
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            rprint(f"[red]Package installation failed: {e}[/]")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            return False

    def _install_windows(self, package_path: Path) -> bool:
        """Install Pylon SDK on Windows from local package.

        Args:
            package_path: Path to the downloaded package

        Returns:
            True if installation successful, False otherwise
        """
        self.logger.info("Installing Pylon SDK for Windows")

        # Check for administrative privileges
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            is_admin = False

        if not is_admin:
            rprint("[yellow]Administrative privileges may be required.[/]")
            rprint("If installation fails, please run as Administrator.")

        try:
            # Run the installer
            rprint("         Running installer...")
            rprint("         [dim]Follow the on-screen prompts to complete installation.[/]")

            if package_path.suffix == ".exe":
                subprocess.run([str(package_path)], check=True)
            elif package_path.suffix == ".zip":
                # Extract and find .exe
                import zipfile

                extract_dir = self.pylon_dir / "temp_extract"
                extract_dir.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(package_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)

                # Find .exe installer
                exe_files = list(extract_dir.rglob("*.exe"))
                if exe_files:
                    subprocess.run([str(exe_files[0])], check=True)
                else:
                    rprint("[red]No executable found in zip file[/]")
                    return False
            else:
                rprint(f"[red]Unsupported package format: {package_path.suffix}[/]")
                return False

            self._show_success_message()
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Installation failed: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            return False

    def _show_success_message(self) -> None:
        """Display installation success message."""
        success_text = """[bold green]Installation Complete![/]

[bold]Installed Tools:[/]
  Pylon Viewer      - For live camera view and configuration
  IP Configurator   - For setting GigE camera IP addresses

[bold]Next Steps:[/]"""

        if self.platform == "Linux":
            success_text += """
  1. Log out and log back in for changes to take effect
  2. Or run: [cyan]source /opt/pylon/bin/pylon-setup-env.sh[/]
  3. Unplug and replug USB cameras if applicable"""
        else:
            success_text += """
  1. Restart any applications that need to access cameras
  2. The tools are available in the Start Menu under 'Basler'"""

        rprint(Panel(success_text, border_style="green"))

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
                rprint(f"[red]Unsupported platform: {self.platform}[/]")
                return False

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            rprint(f"[red]Uninstallation failed: {e}[/]")
            return False

    def _uninstall_linux(self) -> bool:
        """Uninstall Pylon SDK on Linux.

        Returns:
            True if uninstallation successful, False otherwise
        """
        rprint("Uninstalling Pylon SDK from Linux...")

        try:
            # Remove pylon packages
            rprint("Removing pylon packages...")
            subprocess.run(["sudo", "apt-get", "remove", "-y", "pylon*"], check=False)

            # Remove codemeter packages
            rprint("Removing codemeter packages...")
            subprocess.run(["sudo", "apt-get", "remove", "-y", "codemeter*"], check=False)

            # Clean up
            rprint("Cleaning up unused packages...")
            self._run_command(["sudo", "apt-get", "autoremove", "-y"])

            rprint("[green]Pylon SDK uninstalled successfully.[/]")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    def _uninstall_windows(self) -> bool:
        """Uninstall Pylon SDK on Windows.

        Returns:
            False (manual uninstallation required)
        """
        rprint("[yellow]Automatic uninstallation on Windows is not supported.[/]")
        rprint("Please use Windows Settings > Apps to uninstall the Pylon SDK.")
        return False


@app.command()
def install(
    package: Optional[Path] = typer.Option(
        None,
        "--package",
        "-p",
        help="Path to pre-downloaded Pylon SDK package file",
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
    """Install the Basler Pylon SDK using an interactive wizard.

    The wizard will guide you through downloading and installing the SDK
    from Basler's official website where you'll accept their EULA.

    For CI/automation, use --package to provide a pre-downloaded file.
    """
    installer = PylonSDKInstaller(package_path=str(package) if package else None)

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
    """Uninstall the Basler Pylon SDK."""
    installer = PylonSDKInstaller()

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.uninstall()
    raise typer.Exit(code=0 if success else 1)


def main() -> None:
    """Main entry point for the script."""
    app()


if __name__ == "__main__":
    main()  # pragma: no cover
