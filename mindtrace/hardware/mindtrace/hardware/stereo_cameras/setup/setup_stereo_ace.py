#!/usr/bin/env python3
"""Basler Stereo ace Setup Script

This script provides a guided installation wizard for the Basler pylon
Supplementary Package for Stereo ace cameras on Linux systems. The package
provides the GenTL Producer needed to connect and use Stereo ace camera
systems.

Features:
- Interactive guided wizard with browser integration
- Supports both Debian package (.deb) and tar.gz archive installation
- Custom installation path support (default: ~/.local/share/pylon_stereo)
- Environment variable setup for GenTL Producer
- Shell environment script generation
- Support for pre-downloaded packages (--package flag)
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
    python setup_stereo_ace.py                           # Interactive wizard
    python setup_stereo_ace.py --method deb              # Use Debian package
    python setup_stereo_ace.py --method tarball          # Use tar.gz archive
    python setup_stereo_ace.py --package /path/to/file   # Use pre-downloaded file
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

import logging
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from mindtrace.core import Mindtrace
from mindtrace.hardware.core.config import get_hardware_config

# Typer app instance
app = typer.Typer(
    name="stereo-ace-setup",
    help="Install or uninstall the Basler Stereo ace Supplementary Package (guided wizard)",
    add_completion=False,
    rich_markup_mode="rich",
)


class StereoAceInstaller(Mindtrace):
    """Basler Stereo ace Supplementary Package installer with guided wizard.

    This class provides an interactive installation wizard that guides users
    through downloading and installing the Stereo ace package from the official
    Basler website.
    """

    # Basler official download pages
    BASLER_DOWNLOAD_PAGE = "https://www.baslerweb.com/en/downloads/software-downloads/"
    BASLER_DEB_PAGE = "https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-debian/"
    BASLER_TARBALL_PAGE = "https://www.baslerweb.com/en/downloads/software-downloads/pylon-supplementary-package-for-stereo-ace-1-0-3-linux-x86-64-setup-tar-gz/"

    # Package file patterns for validation
    PACKAGE_INFO = {
        "deb": {
            "search_term": "pylon Supplementary Package for Stereo ace - Linux x86 (64 Bit) - Debian",
            "file_pattern": "pylon-supplementary-package-for-stereo-ace*amd64.deb",
            "file_description": "pylon-supplementary-package-for-stereo-ace-X.X.X_amd64.deb",
            "min_size_mb": 50,
            "download_page": BASLER_DEB_PAGE,
        },
        "tarball": {
            "search_term": "pylon Supplementary Package for Stereo ace - Linux x86 (64 Bit) - tar.gz",
            "file_pattern": "pylon-supplementary-package-for-stereo-ace*setup.tar.gz",
            "file_description": "pylon-supplementary-package-for-stereo-ace-X.X.X-Linux_x86_64_setup.tar.gz",
            "min_size_mb": 50,
            "download_page": BASLER_TARBALL_PAGE,
        },
    }

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
            package_path: Path to pre-downloaded package file (optional)
        """
        super().__init__()

        self.hardware_config = get_hardware_config()
        self.platform = platform.system()

        if self.platform != "Linux":
            raise RuntimeError("Stereo ace Supplementary Package is only supported on Linux")

        self.installation_method = installation_method
        self.package_path = Path(package_path) if package_path else None

        # Set installation directory
        if install_dir:
            self.install_dir = Path(install_dir).expanduser()
        else:
            if installation_method == "deb":
                self.install_dir = Path("/opt/pylon")
            else:
                self.install_dir = Path.home() / ".local" / "share" / "pylon_stereo"

        self.logger.info(f"Initializing Stereo ace installer for {self.platform}")
        self.logger.info(f"Installation method: {installation_method}")
        self.logger.info(f"Installation directory: {self.install_dir}")

    def install(self) -> bool:
        """Install the Stereo ace Supplementary Package.

        Returns:
            True if installation successful, False otherwise
        """
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
        package_info = self.PACKAGE_INFO[self.installation_method]

        # Step 1: Display info panel
        self._display_intro()

        # Step 2: Confirm installation method
        self._show_method_info()

        if not typer.confirm("\nProceed with installation?", default=True):
            rprint("[yellow]Installation cancelled.[/]")
            return False

        # Step 3: Open browser
        self._open_download_page(package_info)

        # Step 4: Show download instructions
        self._show_download_instructions(package_info)

        # Step 5: Wait for user to download
        rprint("\n[bold cyan]Step 3/5:[/] Download the package")
        rprint("         Please download the file from the opened browser page.")
        rprint("         Accept the EULA when prompted.\n")

        input("         Press Enter when download is complete...")

        # Step 6: Get file path from user
        package_path = self._prompt_for_file(package_info)
        if not package_path:
            return False

        # Step 7: Install
        return self._install_from_package(package_path)

    def _display_intro(self) -> None:
        """Display introductory information panel."""
        intro_text = """[bold]Basler Stereo ace Installation Wizard[/]

This wizard will help you install the Basler pylon Supplementary Package
for Stereo ace cameras, which provides:

  [cyan]GenTL Producer[/]    - Driver for Stereo ace camera communication
  [cyan]StereoViewer[/]      - GUI for 3D visualization and configuration
  [cyan]Python Samples[/]    - Example code for stereo camera integration

[dim]Note: This package is required for Stereo ace cameras to work with pypylon.[/]

You will be guided to download the package from Basler's official website
where you'll need to accept their End User License Agreement (EULA)."""

        rprint(Panel(intro_text, title="Stereo ace Setup", border_style="blue"))

    def _show_method_info(self) -> None:
        """Show information about the selected installation method."""
        rprint(f"\n[bold]Installation Method:[/] {self.installation_method}")

        if self.installation_method == "deb":
            rprint("  - Requires sudo privileges")
            rprint("  - Installs system-wide to /opt/pylon")
            rprint("  - Automatic environment configuration")
        else:
            rprint("  - No sudo required")
            rprint(f"  - Installs to: {self.install_dir}")
            rprint("  - Manual environment setup required")

    def _open_download_page(self, package_info: dict) -> None:
        """Open Basler download page in default browser."""
        rprint("\n[bold cyan]Step 1/5:[/] Opening Basler download page...")

        download_url = package_info.get("download_page", self.BASLER_DOWNLOAD_PAGE)

        try:
            webbrowser.open(download_url)
            rprint(f"         Browser opened to: [link={download_url}]{download_url}[/]")
        except Exception as e:
            rprint(f"[yellow]         Could not open browser automatically: {e}[/]")
            rprint(f"         Please open manually: {download_url}")

    def _show_download_instructions(self, package_info: dict) -> None:
        """Show download instructions for the selected method."""
        rprint("\n[bold cyan]Step 2/5:[/] Find the correct download")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="dim")
        table.add_column("Value")

        table.add_row("Method:", f"[green]{self.installation_method}[/]")
        table.add_row("Search for:", f"[cyan]{package_info['search_term']}[/]")
        table.add_row("File name:", f"[cyan]{package_info['file_description']}[/]")
        table.add_row("Expected size:", f">{package_info['min_size_mb']} MB")

        rprint(table)

    def _prompt_for_file(self, package_info: dict) -> Optional[Path]:
        """Prompt user for downloaded file path.

        Args:
            package_info: Package-specific information dict

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
            if not self._validate_package(path, package_info):
                if not typer.confirm("         Use this file anyway?", default=False):
                    continue

            rprint(f"[green]         File accepted: {path.name}[/]")
            return path

    def _validate_package(self, path: Path, package_info: dict) -> bool:
        """Validate the downloaded package file.

        Args:
            path: Path to the package file
            package_info: Package-specific information dict

        Returns:
            True if file appears valid, False otherwise
        """
        # Check file size
        size_mb = path.stat().st_size / (1024 * 1024)
        min_size = package_info["min_size_mb"]

        if size_mb < min_size:
            rprint(
                f"[yellow]         Warning: File size ({size_mb:.1f} MB) is smaller than expected (>{min_size} MB)[/]"
            )
            return False

        # Check file name pattern
        name = path.name.lower()
        if "stereo" not in name and "pylon" not in name:
            rprint("[yellow]         Warning: File name doesn't contain 'stereo' or 'pylon'[/]")
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
            if self.installation_method == "deb" or package_path.suffix == ".deb":
                return self._install_debian_package(package_path)
            else:
                return self._install_tarball(package_path)

        except Exception as e:
            self.logger.error(f"Installation failed: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            import traceback

            traceback.print_exc()
            return False

    def _install_debian_package(self, package_path: Path) -> bool:
        """Install using Debian package (.deb).

        Args:
            package_path: Path to the .deb package

        Returns:
            True if installation successful, False otherwise
        """
        rprint("         Installing Debian package...")

        try:
            cmd = ["sudo", "apt-get", "install", "-y", str(package_path)]
            self.logger.debug(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

            self._show_success_message_deb()
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Debian package installation failed: {e}")
            rprint(f"[red]Package installation failed: {e}[/]")
            rprint("Make sure you have sudo privileges.")
            return False

    def _install_tarball(self, package_path: Path) -> bool:
        """Install using tar.gz archive.

        Args:
            package_path: Path to the tar.gz package

        Returns:
            True if installation successful, False otherwise
        """
        rprint("         Installing from tar.gz archive...")

        try:
            import tarfile

            # Create installation directory
            self.install_dir.mkdir(parents=True, exist_ok=True)
            rprint(f"         Installation directory: {self.install_dir}")

            # Extract the package
            rprint("         Extracting package...")

            # Check if it's a setup archive (contains inner tarball)
            if "setup" in package_path.name.lower():
                # Extract setup archive to temp location
                temp_dir = self.install_dir / "temp_extract"
                temp_dir.mkdir(parents=True, exist_ok=True)

                with tarfile.open(package_path, "r:gz") as tar:
                    tar.extractall(path=temp_dir)

                # Find the inner tarball
                inner_tarball = None
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith(".tar.gz") and "pylon-supplementary" in file and "setup" not in file.lower():
                            inner_tarball = Path(root) / file
                            break
                    if inner_tarball:
                        break

                if not inner_tarball:
                    rprint("[red]Could not find inner tarball in package[/]")
                    return False

                rprint(f"         Found inner tarball: {inner_tarball.name}")

                # Extract inner tarball to install_dir
                with tarfile.open(inner_tarball, "r:gz") as tar:
                    tar.extractall(path=self.install_dir)

                # Clean up temp directory
                shutil.rmtree(temp_dir)
            else:
                # Direct extraction
                with tarfile.open(package_path, "r:gz") as tar:
                    tar.extractall(path=self.install_dir)

            # Verify installation
            gentl_path = self.install_dir / "pylon" / "lib" / "gentlproducer" / "gtl" / "basler_xw.cti"
            if not gentl_path.exists():
                # Try alternate path
                gentl_candidates = list(self.install_dir.rglob("*.cti"))
                if gentl_candidates:
                    rprint(f"         GenTL producer found: {gentl_candidates[0]}")
                else:
                    rprint("[yellow]         Warning: GenTL producer not found at expected location[/]")

            # Create environment setup script
            self._create_environment_script()

            # Offer to add to bashrc
            self._offer_bashrc_setup()

            self._show_success_message_tarball()
            return True

        except Exception as e:
            self.logger.error(f"tar.gz installation failed: {e}")
            rprint(f"[red]Installation failed: {e}[/]")
            return False

    def _create_environment_script(self) -> None:
        """Create shell environment setup script."""
        script_path = self.install_dir / "setup_stereo_env.sh"

        script_content = """#!/bin/bash
# Environment setup for Basler Stereo ace cameras
# Generated by Mindtrace Stereo ace installer

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYLON_ROOT="${SCRIPT_DIR}/pylon"

# Set up pylon environment if pylon-setup-env.sh exists
if [ -f "${PYLON_ROOT}/bin/pylon-setup-env.sh" ]; then
    source "${PYLON_ROOT}/bin/pylon-setup-env.sh" "${PYLON_ROOT}"
fi

# Add Stereo ace GenTL producer path
export GENICAM_GENTL64_PATH="${PYLON_ROOT}/lib/gentlproducer/gtl:${GENICAM_GENTL64_PATH}"

# Add to LD_LIBRARY_PATH for runtime library loading
export LD_LIBRARY_PATH="${PYLON_ROOT}/lib:${PYLON_ROOT}/lib/gentlproducer/gtl:${LD_LIBRARY_PATH}"

echo "Basler Stereo ace environment configured:"
echo "  PYLON_ROOT: ${PYLON_ROOT}"
echo "  GENICAM_GENTL64_PATH: ${GENICAM_GENTL64_PATH}"
"""

        with open(script_path, "w") as f:
            f.write(script_content)

        script_path.chmod(0o755)
        rprint(f"         Created environment script: {script_path}")

    def _offer_bashrc_setup(self) -> None:
        """Offer to add environment setup to ~/.bashrc."""
        bashrc_path = Path.home() / ".bashrc"
        script_path = self.install_dir / "setup_stereo_env.sh"
        source_line = f"source {script_path}"

        # Check if already in bashrc
        if bashrc_path.exists():
            with open(bashrc_path, "r") as f:
                if str(script_path) in f.read():
                    rprint("         Environment setup already in ~/.bashrc")
                    return

        # Check if running in interactive terminal
        if sys.stdin.isatty():
            rprint("")
            if typer.confirm("         Add environment setup to ~/.bashrc?", default=False):
                try:
                    with open(bashrc_path, "a") as f:
                        f.write("\n# Basler Stereo ace environment (added by mindtrace)\n")
                        f.write(f"{source_line}\n")
                    rprint("         Added to ~/.bashrc")
                except Exception as e:
                    rprint(f"[red]         Failed to update ~/.bashrc: {e}[/]")
            else:
                rprint(f"         To add manually: echo '{source_line}' >> ~/.bashrc")

    def _show_success_message_deb(self) -> None:
        """Display success message for Debian package installation."""
        success_text = """[bold green]Installation Complete![/]

[bold]Installed Components:[/]
  GenTL Producer    - Driver for Stereo ace camera communication
  StereoViewer      - GUI for 3D visualization
  Python Samples    - Example code in /opt/pylon/share/pylon/Samples/

[bold]Next Steps:[/]
  1. Log out and log back in for changes to take effect
  2. Or run: [cyan]source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon[/]
  3. Verify: [cyan]echo $GENICAM_GENTL64_PATH[/]"""

        rprint(Panel(success_text, border_style="green"))

    def _show_success_message_tarball(self) -> None:
        """Display success message for tarball installation."""
        success_text = f"""[bold green]Installation Complete![/]

[bold]Installed Components:[/]
  GenTL Producer    - Driver for Stereo ace camera communication
  StereoViewer      - GUI for 3D visualization
  Python Samples    - Example code in pylon/share/pylon/Samples/

[bold]Next Steps:[/]
  1. Run: [cyan]source {self.install_dir}/setup_stereo_env.sh[/]
  2. Verify: [cyan]echo $GENICAM_GENTL64_PATH[/]

[dim]To make permanent, add to ~/.bashrc:
  echo 'source {self.install_dir}/setup_stereo_env.sh' >> ~/.bashrc[/]"""

        rprint(Panel(success_text, border_style="green"))

    def uninstall(self) -> bool:
        """Uninstall the Stereo ace Supplementary Package.

        Returns:
            True if uninstallation successful, False otherwise
        """
        self.logger.info("Starting Stereo ace Supplementary Package uninstallation")

        try:
            if self.installation_method == "deb":
                return self._uninstall_debian_package()
            else:
                return self._uninstall_tarball()

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            rprint(f"[red]Uninstallation failed: {e}[/]")
            return False

    def _uninstall_debian_package(self) -> bool:
        """Uninstall Debian package.

        Returns:
            True if uninstallation successful, False otherwise
        """
        rprint("Uninstalling Stereo ace Debian package...")

        try:
            cmd = ["sudo", "apt-get", "remove", "-y", "pylon-supplementary-package-for-stereo-ace"]
            self.logger.debug(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

            rprint("[green]Stereo ace Supplementary Package uninstalled successfully.[/]")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False

    def _uninstall_tarball(self) -> bool:
        """Uninstall tar.gz archive installation.

        Returns:
            True if uninstallation successful, False otherwise
        """
        rprint(f"Uninstalling Stereo ace from {self.install_dir}...")

        if not self.install_dir.exists():
            rprint(f"[yellow]Installation directory not found: {self.install_dir}[/]")
            return True

        try:
            shutil.rmtree(self.install_dir)
            rprint(f"         Removed {self.install_dir}")

            rprint("[green]Stereo ace Supplementary Package uninstalled successfully.[/]")
            rprint("")
            rprint("[dim]Don't forget to remove the environment setup from ~/.bashrc if you added it.[/]")
            return True

        except Exception as e:
            self.logger.error(f"Uninstallation failed: {e}")
            return False


@app.command()
def install(
    method: str = typer.Option(
        "tarball",
        "--method",
        "-m",
        help="Installation method: 'deb' (requires sudo) or 'tarball' (portable)",
    ),
    package: Optional[Path] = typer.Option(
        None,
        "--package",
        "-p",
        help="Path to pre-downloaded package file (.deb or .tar.gz)",
        exists=True,
        dir_okay=False,
    ),
    install_dir: Optional[Path] = typer.Option(
        None,
        "--install-dir",
        "-d",
        help="Custom installation directory (for tarball method)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Install the Basler Stereo ace Supplementary Package using an interactive wizard.

    The wizard will guide you through downloading and installing the package
    from Basler's official website where you'll accept their EULA.

    Methods:
      deb     - Debian package, requires sudo, installs system-wide
      tarball - tar.gz archive, no sudo, installs to user directory

    For CI/automation, use --package to provide a pre-downloaded file.
    """
    # Validate method
    if method not in ("deb", "tarball"):
        raise typer.BadParameter(f"Invalid method: {method}. Must be 'deb' or 'tarball'.")

    try:
        installer = StereoAceInstaller(
            installation_method=method,
            install_dir=str(install_dir) if install_dir else None,
            package_path=str(package) if package else None,
        )
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.install()
    raise typer.Exit(code=0 if success else 1)


@app.command()
def uninstall(
    method: str = typer.Option(
        "tarball",
        "--method",
        "-m",
        help="Installation method used: 'deb' or 'tarball'",
    ),
    install_dir: Optional[Path] = typer.Option(
        None,
        "--install-dir",
        "-d",
        help="Custom installation directory (for tarball method)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Uninstall the Basler Stereo ace Supplementary Package."""
    # Validate method
    if method not in ("deb", "tarball"):
        raise typer.BadParameter(f"Invalid method: {method}. Must be 'deb' or 'tarball'.")

    try:
        installer = StereoAceInstaller(
            installation_method=method,
            install_dir=str(install_dir) if install_dir else None,
        )
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if verbose:
        installer.logger.setLevel(logging.DEBUG)

    success = installer.uninstall()
    raise typer.Exit(code=0 if success else 1)


def main() -> None:
    """Main entry point for the script."""
    app()


if __name__ == "__main__":
    main()
