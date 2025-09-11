import base64
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from mindtrace.automation.label_studio.label_studio_api import LabelStudio
from mindtrace.automation.label_studio.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    StorageAlreadyExistsError,
)


class FakeProject:
    def __init__(self, project_id: int = 1, title: str = "proj"):
        self.id = project_id
        self.title = title
        self._tasks = []
        self._import_calls = []

    # SDK surface used by LabelStudio
    def import_tasks(self, tasks_or_file):
        # Simulate SDK: return list of created task IDs
        self._import_calls.append(tasks_or_file)
        if isinstance(tasks_or_file, (list, dict)):
            # when JSON payload list, return N ids
            n = len(tasks_or_file) if isinstance(tasks_or_file, list) else 1
            return list(range(1, n + 1))
        # when file path string
        return [1]

    def get_tasks(self):
        return self._tasks

    def get_task(self, task_id):
        for t in self._tasks:
            if t.get("id") == task_id:
                return t
        return {"id": task_id, "annotations": []}

    def get_import_storages(self):
        return getattr(self, "_import_storages", [])

    def get_export_storages(self):
        return getattr(self, "_export_storages", [])


class FakeLS(LabelStudio):
    def __init__(self):
        # Intentionally avoid calling super().__init__ to prevent HTTP Client creation
        self.url = "http://localhost"
        self.api_key = "test"
        self.client = SimpleNamespace()  # stub, never used to call network
        # Minimal logger and config used by methods under test
        self.logger = logging.getLogger("FakeLS")
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.config = {
            "MINDTRACE_GCP_CREDENTIALS_PATH": str(Path.cwd() / "fake_creds.json"),
            "MINDTRACE_DEFAULT_HOST_URLS": {"LabelStudio": self.url},
            "MINDTRACE_API_KEYS": {"LabelStudio": self.api_key},
        }

    def get_project(self, *, project_name=None, project_id=None):
        # Route by provided selector to avoid network
        if project_name is not None:
            proj = getattr(self, "_project_by_name", None)
            if proj is None:
                raise ProjectNotFoundError(f"No project found with name: {project_name}")
            return proj
        if project_id is not None:
            return getattr(self, "_project", FakeProject())
        return getattr(self, "_project", FakeProject())

    def _get_project_by_name(self, project_name: str, page_size: int = 100, **query_params):
        # Controlled by tests via attribute
        return getattr(self, "_project_by_name", None)

    def list_projects(self, page_size: int = 100, **query_params):
        return getattr(self, "_projects", [])


def test_create_project_raises_if_exists():
    ls = FakeLS()
    ls._project_by_name = FakeProject(project_id=5, title="exists")
    with pytest.raises(ProjectAlreadyExistsError):
        ls.create_project(project_name="exists", description="d")


def test_get_project_by_name_success_and_not_found():
    ls = FakeLS()
    proj = FakeProject(project_id=10, title="foo")
    ls._project_by_name = proj
    assert ls.get_project(project_name="foo").id == 10

    ls._project_by_name = None
    with pytest.raises(ProjectNotFoundError):
        ls.get_project(project_name="foo")


def test_create_tasks_from_images_batches(tmp_path: Path):
    # Create 23 image files across subdirs
    img_dir = tmp_path / "images"
    (img_dir / "a").mkdir(parents=True)
    (img_dir / "b").mkdir(parents=True)
    files = []
    for i in range(12):
        p = img_dir / "a" / f"img_{i}.jpg"
        p.write_bytes(b"\x00")
        files.append(p)
    for i in range(11):
        p = img_dir / "b" / f"img_{i}.png"
        p.write_bytes(b"\x00")
        files.append(p)

    ls = FakeLS()
    proj = FakeProject(project_id=1)
    ls._project = proj

    created = ls.create_tasks_from_images(project_id=1, local_dir=str(img_dir), recursive=True, batch_size=10)
    # Each file upload returns [1]
    assert created == len(files)
    # Called once per file
    assert len(proj._import_calls) == len(files)


def test_create_gcp_storage_duplicate_title_raises(tmp_path: Path, monkeypatch):
    ls = FakeLS()
    proj = FakeProject(project_id=2)
    # Simulate existing import storage with same computed title
    proj._import_storages = [{"id": 7, "title": "GCS Import bucket/prefix"}]
    ls._project = proj

    # Point creds to a temp file to avoid permanent file creation
    creds_path = tmp_path / "fake_creds.json"
    creds_path.write_text("{}")
    ls.config["MINDTRACE_GCP_CREDENTIALS_PATH"] = str(creds_path)

    with pytest.raises(StorageAlreadyExistsError):
        ls.create_gcp_storage(project_id=2, bucket="bucket", prefix="prefix", storage_type="import")


def test_get_annotations_for_task_and_all():
    ls = FakeLS()
    proj = FakeProject(project_id=3)
    proj._tasks = [
        {"id": 1, "annotations": [{"id": 11}, {"id": 12}]},
        {"id": 2, "annotations": []},
        {"id": 3, "annotations": [{"id": 31}]},
    ]
    ls._project = proj

    anns_one = ls.get_annotations(project_id=3, task_id=1)
    assert isinstance(anns_one, list) and len(anns_one) == 2

    anns_all = ls.get_annotations(project_id=3)
    assert len(anns_all) == 3


def test_extract_gcs_path_from_label_studio_url():
    ls = FakeLS()
    gcs = "gs://my-bucket/path/to/file.jpg"
    encoded = base64.b64encode(gcs.encode()).decode()
    url = f"http://localhost:8080/data/storage/gcs/presign?fileuri={encoded}"
    assert ls._extract_gcs_path_from_label_studio_url(url) == gcs
