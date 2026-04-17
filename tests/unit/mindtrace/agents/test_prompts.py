"""Unit tests for `mindtrace.agents.prompts`."""

from __future__ import annotations

import builtins
import sys
from types import ModuleType
from unittest.mock import Mock, patch

import pytest

from mindtrace.agents.prompts import BinaryContent, ImageUrl, UserPromptPart


def _install_fake_google_cloud(monkeypatch) -> None:
    storage_module = ModuleType("google.cloud.storage")
    cloud_module = ModuleType("google.cloud")
    google_module = ModuleType("google")
    cloud_module.storage = storage_module
    google_module.cloud = cloud_module
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_module)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage_module)


class TestBinaryContent:
    def test_properties_encode_bytes_and_detect_images(self):
        content = BinaryContent(data=b"hello", media_type="image/png")

        assert content.base64 == "aGVsbG8="
        assert content.data_uri == "data:image/png;base64,aGVsbG8="
        assert content.is_image is True

    def test_non_image_media_type_is_not_image(self):
        content = BinaryContent(data=b"hello", media_type="application/pdf")

        assert content.is_image is False

    def test_from_path_reads_bytes_and_guesses_media_type(self, tmp_path):
        path = tmp_path / "sample.txt"
        path.write_text("example", encoding="utf-8")

        content = BinaryContent.from_path(path)

        assert content.data == b"example"
        assert content.media_type == "text/plain"

    def test_from_path_falls_back_to_octet_stream(self, tmp_path):
        path = tmp_path / "sample.unknownext"
        path.write_bytes(b"\x00\x01")

        content = BinaryContent.from_path(path)

        assert content.data == b"\x00\x01"
        assert content.media_type == "application/octet-stream"

    def test_from_path_raises_for_missing_file(self, tmp_path):
        missing = tmp_path / "missing.png"

        with pytest.raises(FileNotFoundError, match="File not found"):
            BinaryContent.from_path(missing)

    def test_from_gcs_uses_provided_client_and_explicit_media_type(self, monkeypatch):
        _install_fake_google_cloud(monkeypatch)
        blob = Mock(content_type="image/png")
        blob.download_as_bytes.return_value = b"gcs-bytes"
        bucket = Mock()
        bucket.blob.return_value = blob
        client = Mock()
        client.bucket.return_value = bucket

        content = BinaryContent.from_gcs("my-bucket", "folder/item.bin", client=client, media_type="application/json")

        client.bucket.assert_called_once_with("my-bucket")
        bucket.blob.assert_called_once_with("folder/item.bin")
        blob.download_as_bytes.assert_called_once_with()
        assert content.data == b"gcs-bytes"
        assert content.media_type == "application/json"

    def test_from_gcs_uses_blob_content_type_before_guessing(self, monkeypatch):
        _install_fake_google_cloud(monkeypatch)
        blob = Mock(content_type="image/jpeg")
        blob.download_as_bytes.return_value = b"jpeg-bytes"
        bucket = Mock()
        bucket.blob.return_value = blob
        client = Mock()
        client.bucket.return_value = bucket

        content = BinaryContent.from_gcs("my-bucket", "folder/item.jpg", client=client)

        assert content.media_type == "image/jpeg"

    def test_from_gcs_guesses_type_and_then_falls_back_to_octet_stream(self, monkeypatch):
        _install_fake_google_cloud(monkeypatch)
        blob = Mock(content_type=None)
        blob.download_as_bytes.return_value = b"archive-bytes"
        bucket = Mock()
        bucket.blob.return_value = blob
        client = Mock()
        client.bucket.return_value = bucket

        guessed = BinaryContent.from_gcs("my-bucket", "archive.tar.gz", client=client)
        unknown = BinaryContent.from_gcs("my-bucket", "archive.nope", client=client)

        assert guessed.media_type == "application/x-tar"
        assert unknown.media_type == "application/octet-stream"

    def test_from_gcs_raises_helpful_error_when_google_cloud_storage_is_missing(self):
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "google.cloud":
                raise ImportError("missing google.cloud")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="google-cloud-storage is required"):
                BinaryContent.from_gcs("bucket", "blob")


class TestPromptTypes:
    def test_image_url_and_user_prompt_part_store_content(self):
        image = ImageUrl(url="https://example.test/image.png")
        prompt = UserPromptPart(content=["hello", image])

        assert image.url == "https://example.test/image.png"
        assert prompt.content == ["hello", image]
