"""Shared unit-test doubles for ``mindtrace.datalake`` (no real Mongo / Motor).

Class-scoped ``@pytest.fixture`` methods on plain test classes are not always collected
consistively across runners; keeping Motor + Mongo ODM patching here scopes it reliably to
everything under ``tests/unit/mindtrace/datalake/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow ``import export_test_utils`` from exporters/ test modules (mirror layout sibling package).
_DL_SUITE_ROOT = Path(__file__).resolve().parent
_EXPORTERS_SUITE_ROOT_STR = str(_DL_SUITE_ROOT / "exporters")
_DL_SUITE_ROOT_STR = str(_DL_SUITE_ROOT)
if _EXPORTERS_SUITE_ROOT_STR not in sys.path:
    sys.path.insert(0, _EXPORTERS_SUITE_ROOT_STR)
# Append (not prepend) suite root so ``export_test_utils`` still resolves inside ``exporters/``.
if _DL_SUITE_ROOT_STR not in sys.path:
    sys.path.append(_DL_SUITE_ROOT_STR)

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datalake_unit_mongo_uri import DATALAKE_UNIT_MONGO_URI

from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.async_datalake import SlowOpsPolicy

_PATCH_MONGO_MINDTRACE_ODM = (
    "mindtrace.datalake.async_datalake.MongoMindtraceODM",
    "mindtrace.database.MongoMindtraceODM",
    "mindtrace.database.backends.mongo_odm.MongoMindtraceODM",
)


@pytest.fixture(autouse=True)
def _mock_motor_client():
    """Stub ``AsyncIOMotorClient`` for any code path that constructs ``AsyncDatalake``."""

    with patch("mindtrace.datalake.async_datalake.AsyncIOMotorClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        yield mock_cls


@pytest.fixture
def mock_odm():
    mock = AsyncMock()
    mock.initialize = AsyncMock(side_effect=lambda *args, **kwargs: setattr(mock, "_is_initialized", True))
    mock.insert = AsyncMock(side_effect=lambda obj: obj)
    mock.find = AsyncMock(return_value=[])
    mock.find_iter = AsyncMock()
    mock.find_window = AsyncMock(return_value=[])
    mock.count_documents = AsyncMock(return_value=0)
    mock.update = AsyncMock(side_effect=lambda obj: obj)
    mock.delete = AsyncMock()
    mock.client = MagicMock()
    mock.client.drop_database = AsyncMock()
    mock.close = MagicMock()
    mock._is_initialized = False
    return mock


@pytest.fixture(autouse=True)
def _patch_mongo_odm_aliases(mock_odm, _mock_motor_client):
    """Constructor calls must never install real Mongo/Beanie ODMs during unit tests."""

    with ExitStack() as stack:
        for target in _PATCH_MONGO_MINDTRACE_ODM:
            stack.enter_context(patch(target, return_value=mock_odm))
        yield


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.default_mount = "temp"
    store.list_mount_info.return_value = {
        "temp": {
            "read_only": False,
            "backend": "file:///tmp/mindtrace-store-test",
            "version_objects": False,
            "mutable": True,
            "version_digits": 6,
        },
        "nas": {
            "read_only": False,
            "backend": "file:///tmp/mindtrace-nas",
            "version_objects": False,
            "mutable": True,
            "version_digits": 6,
        },
        "archive": {
            "read_only": False,
            "backend": "file:///tmp/mindtrace-archive",
            "version_objects": False,
            "mutable": True,
            "version_digits": 6,
        },
    }
    mounts = {mount: MagicMock() for mount in store.list_mount_info.return_value}
    for mount in mounts.values():
        mount.registry = MagicMock()
        mount.registry.clear = MagicMock()
    store.has_mount.side_effect = lambda mount: mount in store.list_mount_info.return_value
    store.list_mounts.side_effect = lambda: sorted(store.list_mount_info.return_value.keys())
    store.get_mount.side_effect = lambda mount: mounts[mount]
    store.clear_location_cache = MagicMock()
    store.build_key.side_effect = lambda mount, name, version=None: (
        f"{mount}/{name}" if version is None else f"{mount}/{name}@{version}"
    )
    store.save.return_value = "v1"
    store.copy.return_value = "v2"
    store.load.return_value = b"payload"
    store.info.return_value = {"size": 123}
    store.has_object.return_value = True
    store.create_direct_upload_target.return_value = {
        "upload_method": "local_path",
        "upload_url": None,
        "upload_path": "/tmp/direct-upload/data.txt",
        "upload_headers": {},
        "staged_target": {"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
    }
    store.inspect_direct_upload_target.return_value = {"exists": True, "size_bytes": 7}
    store.commit_direct_upload.return_value = "v5"
    store.cleanup_direct_upload_target.return_value = True
    return store


@pytest.fixture
def async_datalake(mock_odm, mock_store, _patch_mongo_odm_aliases):
    # ``_patch_mongo_odm_aliases`` pulls autouse Mongo ODM patches in before construct.
    # (Otherwise pytest may build this fixture before those patches activate.)
    return AsyncDatalake(
        DATALAKE_UNIT_MONGO_URI,
        "test_db",
        store=mock_store,
        slow_ops_policy=SlowOpsPolicy.ALLOW,
    )
