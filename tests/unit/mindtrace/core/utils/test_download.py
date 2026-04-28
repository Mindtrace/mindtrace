import io
from pathlib import Path
from unittest import mock

import pytest

from mindtrace.core.utils.download import (
    download_and_extract_tarball,
    download_and_extract_zip,
    download_with_progress,
)


@pytest.fixture
def fake_zip_bytes():
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("test.txt", "This is a test file.")
    zip_buffer.seek(0)
    return zip_buffer


@mock.patch("mindtrace.core.utils.download.tqdm")
@mock.patch("mindtrace.core.utils.download.urlopen")
def test_download_with_progress_reads_chunks(mock_urlopen, mock_tqdm, tmp_path):
    dest = tmp_path / "blob.bin"
    chunk = b"abcd"

    class Resp:
        headers = {"Content-Length": str(len(chunk))}

        def read(self, n=-1):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    mock_urlopen.return_value = Resp()
    mock_bar = mock.MagicMock()
    mock_tqdm.return_value = mock_bar

    out = download_with_progress("http://example.com/x", dest, chunk_size=2)
    assert out == dest
    assert dest.read_bytes() == chunk
    mock_bar.update.assert_called()
    mock_bar.close.assert_called()


@mock.patch("mindtrace.core.utils.download.download_with_progress")
@mock.patch("mindtrace.core.utils.download.tarfile.open")
def test_download_tarball_uses_progress_when_requested(mock_tar_open, mock_dwp, tmp_path):
    mock_dwp.side_effect = lambda url, path, **kw: Path(path).write_bytes(b"x")
    mock_tar = mock.MagicMock()
    mock_tar_open.return_value.__enter__.return_value = mock_tar

    download_and_extract_tarball(
        "http://example.com/x.tar.gz",
        tmp_path,
        filename="x.tar.gz",
        show_progress=True,
    )
    mock_dwp.assert_called_once()


@pytest.fixture
def fake_tar_bytes():
    import tarfile

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="test.txt")
        data = b"This is a test file."
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    tar_buffer.seek(0)
    return tar_buffer


@mock.patch("mindtrace.core.utils.download.urlretrieve")
@mock.patch("mindtrace.core.utils.download.zipfile.ZipFile")
def test_download_and_extract_zip_success(mock_zipfile, mock_urlretrieve, tmp_path, fake_zip_bytes):
    mock_urlretrieve.side_effect = lambda url, path: Path(path).write_bytes(fake_zip_bytes.read())

    mock_zip = mock.MagicMock()
    mock_zipfile.return_value.__enter__.return_value = mock_zip

    result_path = download_and_extract_zip("http://example.com/test.zip", tmp_path)
    assert result_path == tmp_path
    mock_zip.extractall.assert_called_once_with(tmp_path)


@mock.patch("mindtrace.core.utils.download.Path.unlink")
@mock.patch("mindtrace.core.utils.download.Path.exists", return_value=True)
@mock.patch("mindtrace.core.utils.download.urlretrieve", side_effect=Exception("Download failed"))
def test_download_and_extract_zip_failure_unlink(mock_urlretrieve, mock_exists, mock_unlink, tmp_path):
    with pytest.raises(Exception, match="Download failed"):
        download_and_extract_zip("http://example.com/fail.zip", tmp_path)
    mock_unlink.assert_called_once()


@mock.patch("mindtrace.core.utils.download.urlretrieve")
@mock.patch("mindtrace.core.utils.download.tarfile.open")
def test_download_and_extract_tarball_success(mock_tar_open, mock_urlretrieve, tmp_path, fake_tar_bytes):
    mock_urlretrieve.side_effect = lambda url, path: Path(path).write_bytes(fake_tar_bytes.read())

    mock_tar = mock.MagicMock()
    mock_tar_open.return_value.__enter__.return_value = mock_tar

    result_path = download_and_extract_tarball("http://example.com/test.tar.gz", tmp_path)
    assert result_path == tmp_path
    mock_tar.extractall.assert_called_once_with(tmp_path)


@mock.patch("mindtrace.core.utils.download.Path.unlink")
@mock.patch("mindtrace.core.utils.download.Path.exists", return_value=True)
@mock.patch("mindtrace.core.utils.download.urlretrieve", side_effect=Exception("Download failed"))
def test_download_and_extract_tarball_failure_unlink(mock_urlretrieve, mock_exists, mock_unlink, tmp_path):
    with pytest.raises(Exception, match="Download failed"):
        download_and_extract_tarball("http://example.com/fail.tar.gz", tmp_path)
    mock_unlink.assert_called_once()


def test_default_zip_filename(tmp_path):
    with (
        mock.patch("mindtrace.core.utils.download.urlretrieve") as mock_urlretrieve,
        mock.patch("mindtrace.core.utils.download.zipfile.ZipFile") as mock_zipfile,
    ):
        mock_zip = mock.MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        download_and_extract_zip("http://example.com/archive", tmp_path)
        args, kwargs = mock_urlretrieve.call_args
        assert args[0] == "http://example.com/archive"
        assert str(args[1]).endswith(".zip")


def test_tarball_mode_detection(tmp_path):
    extensions_modes = {
        "test.tar.gz": "r:gz",
        "test.tgz": "r:gz",
        "test.tar.bz2": "r:bz2",
        "test.tbz2": "r:bz2",
        "test.tar.xz": "r:xz",
        "test.txz": "r:xz",
        "test.tar": "r",
    }

    for filename, expected_mode in extensions_modes.items():
        with (
            mock.patch("mindtrace.core.utils.download.urlretrieve") as mock_urlretrieve,
            mock.patch("mindtrace.core.utils.download.tarfile.open") as mock_tar_open,
        ):
            mock_tar = mock.MagicMock()
            mock_tar_open.return_value.__enter__.return_value = mock_tar

            mock_urlretrieve.side_effect = lambda url, path: Path(path).write_text("dummy")
            download_and_extract_tarball(f"http://example.com/{filename}", tmp_path, filename=filename)
            mock_tar_open.assert_called_once()
            called_path, called_mode = mock_tar_open.call_args[0]
            assert called_mode == expected_mode


def test_download_and_extract_zip_failure_no_file_to_unlink(tmp_path):
    with (
        mock.patch("mindtrace.core.utils.download.urlretrieve", side_effect=Exception("Download failed")),
        mock.patch("mindtrace.core.utils.download.Path.exists", return_value=False),
        mock.patch("mindtrace.core.utils.download.Path.unlink") as mock_unlink,
    ):
        with pytest.raises(Exception, match="Download failed"):
            download_and_extract_zip("http://example.com/fail.zip", tmp_path)
        mock_unlink.assert_not_called()


def test_download_and_extract_zip_failure_unlink_raises(tmp_path):
    with (
        mock.patch("mindtrace.core.utils.download.urlretrieve", side_effect=Exception("Download failed")),
        mock.patch("mindtrace.core.utils.download.Path.exists", return_value=True),
        mock.patch("mindtrace.core.utils.download.Path.unlink", side_effect=Exception("Unlink failed")) as mock_unlink,
    ):
        with pytest.raises(Exception, match="Download failed"):
            download_and_extract_zip("http://example.com/fail.zip", tmp_path)
        mock_unlink.assert_called_once()


def test_download_and_extract_tarball_failure_no_file_to_unlink(tmp_path):
    with (
        mock.patch("mindtrace.core.utils.download.urlretrieve", side_effect=Exception("Download failed")),
        mock.patch("mindtrace.core.utils.download.Path.exists", return_value=False),
        mock.patch("mindtrace.core.utils.download.Path.unlink") as mock_unlink,
    ):
        with pytest.raises(Exception, match="Download failed"):
            download_and_extract_tarball("http://example.com/fail.tar.gz", tmp_path)
        mock_unlink.assert_not_called()


def test_download_and_extract_tarball_failure_unlink_raises(tmp_path):
    with (
        mock.patch("mindtrace.core.utils.download.urlretrieve", side_effect=Exception("Download failed")),
        mock.patch("mindtrace.core.utils.download.Path.exists", return_value=True),
        mock.patch("mindtrace.core.utils.download.Path.unlink", side_effect=Exception("Unlink failed")) as mock_unlink,
    ):
        with pytest.raises(Exception, match="Download failed"):
            download_and_extract_tarball("http://example.com/fail.tar.gz", tmp_path)
        mock_unlink.assert_called_once()
