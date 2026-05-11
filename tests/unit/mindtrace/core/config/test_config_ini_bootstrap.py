"""Tests for optional ``config.ini`` bootstrap from ``config.ini.example``."""

from __future__ import annotations

import mindtrace.core.config.config as config_module


def test_bootstrap_copies_example_when_config_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_PACKAGE_CONFIG_DIR", tmp_path)
    (tmp_path / "config.ini.example").write_text(
        "[MINDTRACE_LOGGER]\nUSE_STRUCTLOG = False\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    ok = config_module.bootstrap_config_ini_from_example()
    assert ok
    assert (tmp_path / "config.ini").read_text(encoding="utf-8") == (tmp_path / "config.ini.example").read_text(
        encoding="utf-8"
    )


def test_bootstrap_skips_when_config_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_PACKAGE_CONFIG_DIR", tmp_path)
    (tmp_path / "config.ini").write_text("[M]\nK=v\n", encoding="utf-8")
    (tmp_path / "config.ini.example").write_text("[OTHER]\nX=1\n", encoding="utf-8")

    ok = config_module.bootstrap_config_ini_from_example()
    assert ok
    assert (tmp_path / "config.ini").read_text(encoding="utf-8") == "[M]\nK=v\n"


def test_bootstrap_skipped_when_opt_out(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "_PACKAGE_CONFIG_DIR", tmp_path)
    monkeypatch.setenv("MINDTRACE_SKIP_CONFIG_INI_BOOTSTRAP", "1")
    (tmp_path / "config.ini.example").write_text("[M]\nK=1\n", encoding="utf-8")

    assert not config_module.bootstrap_config_ini_from_example()
    assert not (tmp_path / "config.ini").exists()


def test_bootstrap_copies_example_when_ci_flags_set(tmp_path, monkeypatch):
    """GitHub sets ``CI`` + ``GITHUB_ACTIONS`` — bootstrap still runs."""

    monkeypatch.setattr(config_module, "_PACKAGE_CONFIG_DIR", tmp_path)
    (tmp_path / "config.ini.example").write_text("[M]\nKEY = ci\n", encoding="utf-8")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    ok = config_module.bootstrap_config_ini_from_example()
    assert ok
    assert (tmp_path / "config.ini").read_text(encoding="utf-8") == (tmp_path / "config.ini.example").read_text(
        encoding="utf-8"
    )


def test_load_ini_settings_triggers_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_PACKAGE_CONFIG_DIR", tmp_path)
    (tmp_path / "config.ini.example").write_text("[SECT]\nKEY = value\n", encoding="utf-8")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("MINDTRACE_SKIP_CONFIG_INI_BOOTSTRAP", raising=False)

    data = config_module.load_ini_settings()
    assert data["SECT"]["KEY"] == "value"
    assert (tmp_path / "config.ini").exists()
