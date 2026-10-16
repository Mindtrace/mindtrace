"""Store presign routing against a real remote mount.

Local backends return ``None`` for ``create_direct_download_url``, so this
contract is only observable when an object lives on S3 or GCS.
"""

from __future__ import annotations

import urllib.request
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.registry]


class TestStoreRemoteBugHunt:
    """S2: unqualified presign must use the mount ``load()`` would hit."""

    def test_s2_unqualified_direct_download_url_uses_discovered_mount(self, remote_and_local_store, remote_kind):
        """Unqualified create_direct_download_url must presign the mount load() would hit, not only default_mount."""
        store = remote_and_local_store
        name = f"item-{uuid.uuid4().hex[:8]}"
        payload = {"ok": True, "id": name}
        store.save(f"remote/{name}", payload)

        assert store.load(name) == payload

        url = store.create_direct_download_url(name)
        assert url is not None
        assert isinstance(url, str)
        assert url.startswith("http")

        if remote_kind == "s3":
            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 — signed URL to test S3
                assert response.status == 200
                body = response.read()
            assert body


def test_local_presign_returns_none_for_existing_object(remote_and_local_store):
    store = remote_and_local_store
    store.save("local/control", b"control")
    assert store.create_direct_download_url("local/control") is None


def test_missing_local_presign_raises_not_found(remote_and_local_store):
    from mindtrace.registry.core.exceptions import RegistryObjectNotFound

    with pytest.raises(RegistryObjectNotFound):
        remote_and_local_store.create_direct_download_url("local/absent")
