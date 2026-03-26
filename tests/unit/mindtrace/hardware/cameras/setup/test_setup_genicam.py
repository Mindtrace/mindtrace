"""Tests for GenICam setup utilities and CLI wrappers."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from mindtrace.hardware.cameras.setup.setup_genicam import (
    GenICamCTIInstaller,
    app,
    install_genicam_cti,
    uninstall_genicam_cti,
    verify_genicam_cti,
)

runner = CliRunner()


def _mock_hw_config():
    cfg = Mock()
    cfg.paths.lib_dir = "/tmp"
    hw = Mock()
    hw.get_config.return_value = cfg
    return hw


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_verify_installation_missing_file(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Linux"
    with patch("os.path.exists", return_value=False):
        assert inst.verify_installation() is False


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_verify_installation_small_file_fails(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Linux"
    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=512 * 1024):
        assert inst.verify_installation() is False


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_verify_installation_large_file_succeeds(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Linux"
    with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=2 * 1024 * 1024):
        assert inst.verify_installation() is True


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_install_dispatch_unsupported_platform(_):
    inst = GenICamCTIInstaller()
    inst.platform = "Solaris"
    assert inst.install() is False


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_find_install_script(_):
    inst = GenICamCTIInstaller()
    with patch("os.path.exists", side_effect=lambda p: p == "setup.sh"):
        assert inst._find_install_script() == "setup.sh"


@patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=_mock_hw_config())
def test_wrapper_functions_delegate(_):
    with patch.object(GenICamCTIInstaller, "install", return_value=True) as mi:
        assert install_genicam_cti() is True
        mi.assert_called_once()
    with patch.object(GenICamCTIInstaller, "uninstall", return_value=False) as mu:
        assert uninstall_genicam_cti() is False
        mu.assert_called_once()
    with patch.object(GenICamCTIInstaller, "verify_installation", return_value=True) as mv:
        assert verify_genicam_cti() is True
        mv.assert_called_once()


@patch("mindtrace.hardware.cameras.setup.setup_genicam.GenICamCTIInstaller")
def test_cli_verify_success(mock_installer):
    inst = Mock()
    inst.verify_installation.return_value = True
    inst.logger = Mock()
    mock_installer.return_value = inst

    result = runner.invoke(app, ["verify"])
    assert result.exit_code == 0


@patch("mindtrace.hardware.cameras.setup.setup_genicam.GenICamCTIInstaller")
def test_cli_install_failure(mock_installer):
    inst = Mock()
    inst.install.return_value = False
    inst.logger = Mock()
    mock_installer.return_value = inst

    result = runner.invoke(app, ["install"])
    assert result.exit_code == 1
