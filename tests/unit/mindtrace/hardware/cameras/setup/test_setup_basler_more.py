"""Additional branch tests for Basler setup installer."""

from unittest.mock import Mock, patch

import pytest

from mindtrace.hardware.cameras.setup.setup_basler import PylonSDKInstaller


@pytest.fixture
def installer(tmp_path):
    cfg = Mock()
    cfg.paths.lib_dir = str(tmp_path)
    hw = Mock()
    hw.get_config.return_value = cfg

    with patch("mindtrace.hardware.cameras.setup.setup_basler.get_hardware_config", return_value=hw):
        inst = PylonSDKInstaller()
    return inst


def test_prompt_for_file_quit(installer):
    with patch("mindtrace.hardware.cameras.setup.setup_basler.typer.prompt", return_value="q"):
        assert installer._prompt_for_file(installer.PLATFORM_INFO["Linux"]) is None


def test_prompt_for_file_accepts_valid_path(installer, tmp_path):
    pkg = tmp_path / "pylon_ok.tar.gz"
    pkg.write_bytes(b"x" * (150 * 1024 * 1024))

    with patch("mindtrace.hardware.cameras.setup.setup_basler.typer.prompt", return_value=str(pkg)):
        got = installer._prompt_for_file(installer.PLATFORM_INFO["Linux"])

    assert got == pkg


def test_open_download_page_handles_browser_error(installer):
    with patch("mindtrace.hardware.cameras.setup.setup_basler.webbrowser.open", side_effect=RuntimeError("boom")):
        installer._open_download_page()  # no raise


def test_install_from_package_dispatches_linux(installer, tmp_path):
    installer.platform = "Linux"
    pkg = tmp_path / "pylon.tar.gz"
    pkg.write_text("x")

    with patch.object(installer, "_install_linux", return_value=True) as m:
        assert installer._install_from_package(pkg) is True
        m.assert_called_once_with(pkg)


def test_install_from_package_dispatches_windows(installer, tmp_path):
    installer.platform = "Windows"
    pkg = tmp_path / "pylon.exe"
    pkg.write_text("x")

    with patch.object(installer, "_install_windows", return_value=True) as m:
        assert installer._install_from_package(pkg) is True
        m.assert_called_once_with(pkg)


def test_install_linux_installs_debs(installer, tmp_path):
    installer.platform = "Linux"
    installer.pylon_dir = tmp_path / "pylon"
    pkg = tmp_path / "pylon_debs.tar.gz"
    pkg.write_bytes(b"x")

    deb1 = installer.pylon_dir / "a.deb"
    deb2 = installer.pylon_dir / "sub" / "b.deb"
    deb2.parent.mkdir(parents=True, exist_ok=True)
    deb1.write_text("a")
    deb2.write_text("b")

    class DummyTar:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extractall(self, path):
            return None

    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    with patch("tarfile.open", return_value=DummyTar()), patch.object(installer, "_run_command", side_effect=fake_run):
        ok = installer._install_linux(pkg)

    assert ok is True
    assert any(cmd[:3] == ["sudo", "apt-get", "update"] for cmd in calls)
    assert any(cmd[:3] == ["sudo", "dpkg", "-i"] for cmd in calls)


def test_uninstall_linux_runs_cleanup(installer):
    installer.platform = "Linux"

    calls = []

    def fake_subprocess_run(cmd, check=False):
        calls.append((cmd, check))
        return Mock()

    with patch("subprocess.run", side_effect=fake_subprocess_run), patch.object(installer, "_run_command") as rc:
        assert installer._uninstall_linux() is True
        rc.assert_called_once_with(["sudo", "apt-get", "autoremove", "-y"])

    assert any(c[0][:4] == ["sudo", "apt-get", "remove", "-y"] for c in calls)


def test_uninstall_windows_returns_false(installer):
    installer.platform = "Windows"
    assert installer._uninstall_windows() is False
