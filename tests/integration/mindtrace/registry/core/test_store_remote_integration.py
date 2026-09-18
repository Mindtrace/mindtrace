"""Store presign routing against a real remote mount.

Local backends return ``None`` for ``create_direct_download_url``, so this
contract is only observable when an object lives on MinIO or GCS.
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
        assert store.create_direct_download_url(f"local/{name}") is None

        url = store.create_direct_download_url(name)
        assert url is not None
        assert isinstance(url, str)
        assert url.startswith("http")

        if remote_kind == "minio":
            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 — signed URL to test MinIO
                assert response.status == 200
                body = response.read()
            assert body
