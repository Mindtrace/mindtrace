"""Tests for stress-suite remote Mongo (Atlas) resolution."""

import pytest

import tests.stress.lib.remote_mongo as remote_mongo
from tests.stress.lib.remote_mongo import resolve_stress_atlas_mongo


def test_resolve_stress_atlas_mongo_prefers_remote_keys():
    uri, db = resolve_stress_atlas_mongo(
        {
            "REMOTE_MONGO_DB_URI": "mongodb+srv://x",
            "REMOTE_MONGO_DB_NAME": "atlas_ns",
            "mongo_atlas_uri": "mongodb+srv://y",
            "mongo_atlas_db_name": "other",
        },
        "fallback_db",
    )
    assert uri == "mongodb+srv://x"
    assert db == "atlas_ns"


def test_resolve_stress_atlas_mongo_legacy_aliases():
    uri, db = resolve_stress_atlas_mongo(
        {"mongo_atlas_uri": "mongodb+srv://legacy", "mongo_atlas_db_name": "ldb"},
        "fallback_db",
    )
    assert uri == "mongodb+srv://legacy"
    assert db == "ldb"


def test_resolve_stress_atlas_mongo_requires_uri(monkeypatch):
    monkeypatch.setattr(remote_mongo, "remote_mongo_from_core_config", lambda: (None, None))
    with pytest.raises(ValueError, match="REMOTE_MONGO_DB_URI"):
        resolve_stress_atlas_mongo({}, "fallback")


def test_resolve_stress_atlas_from_config_fallback(monkeypatch):
    monkeypatch.setattr(
        remote_mongo,
        "remote_mongo_from_core_config",
        lambda: ("mongodb+srv://cfg", "cfgdb"),
    )
    uri, db = resolve_stress_atlas_mongo({}, "fallback")
    assert uri == "mongodb+srv://cfg"
    assert db == "cfgdb"


def test_resolve_run_scoped_mongo_db_before_default(monkeypatch):
    monkeypatch.setattr(
        remote_mongo,
        "remote_mongo_from_core_config",
        lambda: ("mongodb+srv://c", None),
    )
    uri, db = resolve_stress_atlas_mongo({"mongo_db_name": "run_specific"}, "default_db")
    assert uri == "mongodb+srv://c"
    assert db == "run_specific"
