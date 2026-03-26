"""Additional branch tests for GenICam CTI setup installer."""

from unittest.mock import Mock, patch

from mindtrace.hardware.cameras.setup.setup_genicam import GenICamCTIInstaller


def _installer(tmp_path):
    cfg = Mock()
    cfg.paths.lib_dir = str(tmp_path)
    hw = Mock()
    hw.get_config.return_value = cfg
    with patch("mindtrace.hardware.cameras.setup.setup_genicam.get_hardware_config", return_value=hw):
        return GenICamCTIInstaller()


def test_get_cti_path_unknown_platform_returns_empty(tmp_path):
    inst = _installer(tmp_path)
    inst.platform = "Unknown"
    assert inst.get_cti_path() == ""


def test_install_dispatch_windows_and_macos(tmp_path):
    inst = _installer(tmp_path)

    inst.platform = "Windows"
    with patch.object(inst, "_install_windows", return_value=True) as w:
        assert inst.install() is True
        w.assert_called_once()

    inst.platform = "Darwin"
    with patch.object(inst, "_install_macos", return_value=False) as m:
        assert inst.install() is False
        m.assert_called_once()


def test_install_linux_manual_with_debs(tmp_path):
    inst = _installer(tmp_path)

    deb = tmp_path / "a.deb"
    deb.write_text("x")

    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    with patch("pathlib.Path.glob", return_value=[deb]), patch.object(inst, "_run_command", side_effect=fake_run):
        inst._install_linux_manual()

    assert ["sudo", "dpkg", "-i", str(deb)] in calls
    assert ["sudo", "apt-get", "-f", "install", "-y"] in calls


def test_install_linux_manual_without_debs(tmp_path):
    inst = _installer(tmp_path)

    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    with patch("pathlib.Path.glob", return_value=[]), patch.object(inst, "_run_command", side_effect=fake_run):
        inst._install_linux_manual()

    assert ["sudo", "mkdir", "-p", "/opt/ImpactAcquire"] in calls
    assert ["sudo", "chmod", "-R", "755", "/opt/ImpactAcquire"] in calls


def test_find_install_script_none_when_missing(tmp_path):
    inst = _installer(tmp_path)
    with patch("os.path.exists", return_value=False):
        assert inst._find_install_script() is None
