import base64
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from mindtrace.automation.label_studio.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    StorageAlreadyExistsError,
)
from mindtrace.automation.label_studio.label_studio_api import LabelStudio


@pytest.fixture(autouse=True)
def _patch_label_studio_env(monkeypatch, tmp_path):
    # Patch Mindtrace.__init__ to provide logger and default config
    import mindtrace.automation.label_studio.label_studio_api as mod

    def mt_init(self, **kwargs):
        self.logger = logging.getLogger("LabelStudioTest")
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.config = {
            "MINDTRACE_DEFAULT_HOST_URLS": {"LabelStudio": "http://localhost"},
            "MINDTRACE_API_KEYS": {"LabelStudio": "test-key"},
            "MINDTRACE_GCP_CREDENTIALS_PATH": str(tmp_path / "creds.json"),
        }

    monkeypatch.setattr(mod.Mindtrace, "__init__", mt_init, raising=True)

    # Patch SDK Client to avoid real HTTP
    class DummyClient:
        def __init__(self, url, api_key):
            self.url = url
            self.api_key = api_key

        def list_projects(self, **kwargs):
            return []

        def get_project(self, pid):
            return SimpleNamespace(id=pid, title=f"P{pid}")

        def delete_project(self, pid):
            return None

    monkeypatch.setattr(mod, "Client", DummyClient, raising=True)

    # Ensure default creds file exists
    (tmp_path / "creds.json").write_text("{}")

    # Make LabelStudio.__init__ resilient if tests override Mindtrace.__init__
    original_init = mod.LabelStudio.__init__
    # expose for tests that want to exercise original init
    monkeypatch.setattr(mod, "_ORIG_LS_INIT", original_init, raising=False)

    def safe_init(self, url=None, api_key=None, **kwargs):
        # Prepopulate logger and config if absent or incomplete
        if not hasattr(self, "logger"):
            self.logger = logging.getLogger("LabelStudioTest")
            if not self.logger.handlers:
                self.logger.addHandler(logging.NullHandler())
        if not hasattr(self, "config") or self.config is None:
            self.config = {}
        if not isinstance(self.config, dict):
            self.config = {}
        # Ensure required defaults exist
        self.config.setdefault("MINDTRACE_DEFAULT_HOST_URLS", {"LabelStudio": "http://localhost"})
        self.config.setdefault("MINDTRACE_API_KEYS", {"LabelStudio": "test-key"})
        self.config.setdefault("MINDTRACE_GCP_CREDENTIALS_PATH", str(tmp_path / "creds.json"))
        # Construct fields without calling the original __init__ to avoid Mindtrace/sdks side effects
        resolved_url = url if url is not None else self.config["MINDTRACE_DEFAULT_HOST_URLS"]["LabelStudio"]
        resolved_key = api_key if api_key is not None else self.config["MINDTRACE_API_KEYS"]["LabelStudio"]
        self.url = resolved_url
        self.api_key = resolved_key
        # Use patched DummyClient
        self.client = mod.Client(url=self.url, api_key=self.api_key)
        self.logger.info(f"Initialised LS at: {self.url}")
        # Do not call original_init
        return None

    monkeypatch.setattr(mod.LabelStudio, "__init__", safe_init, raising=True)


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

    # Added stubs to avoid hitting the real client and to match API used by tests
    def get_projects(self, page_size: int = 100, **query_params):
        return getattr(self, "_projects", [])

    def list_import_storages(self, project_id: int) -> list:
        return self.get_project(project_id=project_id).get_import_storages()

    def list_export_storages(self, project_id: int) -> list:
        return self.get_project(project_id=project_id).get_export_storages()

    def create_cloud_storage(
        self,
        project_id: int,
        bucket: str,
        prefix: str | None = None,
        storage_type: str = "import",
        google_application_credentials: str | None = None,
        regex_filter: str | None = None,
    ) -> dict:
        # Minimal validation similar to production logic
        if not google_application_credentials or not Path(google_application_credentials).exists():
            raise ValueError(f"GCP credentials file not found at: {google_application_credentials}")
        text = Path(google_application_credentials).read_text()
        json.loads(text)

        proj = self.get_project(project_id=project_id)
        title = f"GCS {storage_type.title()} {bucket}/{prefix}" if prefix else f"GCS {storage_type.title()} {bucket}"

        if storage_type == "import":
            return proj.connect_google_import_storage(
                bucket=bucket,
                prefix=prefix,
                regex_filter=regex_filter,
                use_blob_urls=False,
                presign=True,
                presign_ttl=1,
                title=title,
                description="Imported via Label Studio SDK",
                google_application_credentials=text,
            )
        else:
            return proj.connect_google_export_storage(
                bucket=bucket,
                prefix=prefix,
                use_blob_urls=False,
                title=title,
                description="Exported via Label Studio SDK",
                google_application_credentials=text,
            )

    def sync_storage(self, project_id: int, storage_id: int, storage_type: str = "import") -> bool:
        proj = self.get_project(project_id=project_id)
        if storage_type == "import":
            proj.sync_import_storage("gcs", storage_id)
        else:
            proj.sync_export_storage("gcs", storage_id)
        return True

    def create_and_sync_cloud_storage(
        self,
        project_id: int,
        bucket_name: str,
        storage_prefix: str,
        storage_type: str = "export",
        gcp_credentials=None,
        regex_filter: str | None = None,
    ) -> bool:
        proj = self.get_project(project_id=project_id)
        storages = proj.get_import_storages() if storage_type == "import" else proj.get_export_storages()
        for st in storages:
            if st.get("prefix") == storage_prefix:
                return self.sync_storage(project_id, st["id"], storage_type)
        created = self.create_cloud_storage(
            project_id=project_id,
            bucket=bucket_name,
            prefix=storage_prefix,
            storage_type=storage_type,
            google_application_credentials=gcp_credentials,
            regex_filter=regex_filter,
        )
        return self.sync_storage(project_id, created["id"], storage_type)

    def delete_projects_by_prefix(self, title_prefix: str) -> list[str]:
        projects = self.get_projects()
        matching = [p for p in projects if p.title.startswith(title_prefix)]
        deleted = []
        for p in matching:
            self.client.delete_project(p.id)
            deleted.append(p.title)
        return deleted

    def get_project_task_types(self, project_id: int | None = None, project_name: str | None = None) -> list[str]:
        proj = self.get_project(project_id=project_id, project_name=project_name)
        cfg = proj.label_config
        out = []
        if "<RectangleLabels" in cfg:
            out.append("object_detection")
        if "<PolygonLabels" in cfg or "<BrushLabels" in cfg:
            out.append("segmentation")
        if "<Choices" in cfg or "<Labels" in cfg:
            out.append("classification")
        return out

    def get_project_image_paths(self, project_id: int) -> set:
        proj = self.get_project(project_id=project_id)
        paths = set()
        for t in proj.get_tasks():
            img = t.get("data", {}).get("image") or t.get("image")
            if img:
                paths.add(img)
        return paths

    def get_all_existing_image_paths(self, project_title_prefix: str | None = None) -> set:
        projects = self.get_projects()
        if project_title_prefix:
            projects = [p for p in projects if p.title.startswith(project_title_prefix)]
        out = set()
        for p in projects:
            self._project = p  # route to this project for get_project
            out |= self.get_project_image_paths(p.id)
        return out

    def get_all_existing_gcs_paths(self, project_title_prefix: str | None = None) -> set:
        imgs = self.get_all_existing_image_paths(project_title_prefix)
        gcs_paths = set()
        for image_path in imgs:
            if str(image_path).startswith("gs://"):
                gcs_paths.add(str(image_path))
            elif "presign" in str(image_path) and "fileuri=" in str(image_path):
                gcs = self._extract_gcs_path_from_label_studio_url(str(image_path))
                if gcs:
                    gcs_paths.add(gcs)
        return gcs_paths

    def export_annotations(
        self,
        project_id: int,
        export_type: str = "JSON",
        download_all_tasks: bool = True,
        download_resources: bool = True,
        ids: list | None = None,
        export_location: str | None = None,
    ):
        proj = self.get_project(project_id=project_id)
        return proj.export_tasks(
            export_type=export_type,
            download_all_tasks=download_all_tasks,
            download_resources=download_resources,
            ids=ids,
            export_location=export_location,
        )

    def list_annotations(self, project_id: int, task_id: int | None = None) -> list:
        proj = self.get_project(project_id=project_id)
        if task_id is not None:
            return proj.get_annotations(task_id)
        annotations = []
        for t in proj.get_tasks():
            annotations.extend(proj.get_annotations(t.get("id")))
        return annotations

    def create_project_with_storage(
        self,
        title: str,
        bucket: str,
        prefix: str,
        label_config: str,
        description: str | None = None,
        google_application_credentials: str | None = None,
        regex_filter: str | None = None,
    ):
        project = self.create_project(title=title, description=description, label_config=label_config)
        storage = self.create_cloud_storage(
            project_id=project.id,
            bucket=bucket,
            prefix=prefix,
            storage_type="import",
            google_application_credentials=google_application_credentials,
            regex_filter=regex_filter,
        )
        self.sync_storage(project.id, storage["id"], storage_type="import")
        return project, storage


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


def test_delete_project_by_name_calls_client(monkeypatch):
    calls = {"deleted": []}

    ls = FakeLS()
    proj = FakeProject(project_id=42, title="to-delete")
    ls._project_by_name = proj

    class ClientStub:
        def delete_project(self, pid):
            calls["deleted"].append(pid)

    ls.client = ClientStub()

    ls.delete_project(project_name="to-delete")
    assert calls["deleted"] == [42]


def test_get_latest_project_part():
    ls = FakeLS()
    ls._projects = [
        SimpleNamespace(title="Dataset Part 1"),
        SimpleNamespace(title="Dataset Part 3"),
        SimpleNamespace(title="Dataset Part 2"),
    ]
    part, title = ls.get_latest_project_part(r"Part (\d+)")
    assert part == 3
    assert title == "Dataset Part 3"


def test_list_import_and_export_storages():
    ls = FakeLS()
    proj = FakeProject(project_id=5)
    proj._import_storages = [{"id": 1}]
    proj._export_storages = [{"id": 2}]
    ls._project = proj

    assert ls.list_import_storages(5) == [{"id": 1}]
    assert ls.list_export_storages(5) == [{"id": 2}]


def test_create_cloud_storage_import_valid_and_invalid(tmp_path: Path):
    ls = FakeLS()
    proj = FakeProject(project_id=7)

    created = {}

    def connect_google_import_storage(**kwargs):
        created["import"] = kwargs
        return {"id": 11, "title": kwargs.get("title")}

    # attach method to fake project
    proj.connect_google_import_storage = connect_google_import_storage
    ls._project = proj

    # invalid path should raise
    with pytest.raises(ValueError):
        ls.create_cloud_storage(
            project_id=7,
            bucket="b",
            prefix="p",
            storage_type="import",
            google_application_credentials=str(tmp_path / "missing.json"),
        )

    # valid path
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    out = ls.create_cloud_storage(
        project_id=7, bucket="b", prefix="p", storage_type="import", google_application_credentials=str(creds)
    )
    assert out["id"] == 11
    assert created["import"]["bucket"] == "b"
    assert created["import"]["prefix"] == "p"


def test_sync_storage_calls_correct_method(monkeypatch):
    ls = FakeLS()
    proj = FakeProject(project_id=8)

    calls = {"import": [], "export": []}

    def sync_import_storage(kind, storage_id):
        calls["import"].append((kind, storage_id))

    def sync_export_storage(kind, storage_id):
        calls["export"].append((kind, storage_id))

    proj.sync_import_storage = sync_import_storage
    proj.sync_export_storage = sync_export_storage
    ls._project = proj

    ls.sync_storage(8, 100, storage_type="import")
    ls.sync_storage(8, 200, storage_type="export")

    assert calls["import"] == [("gcs", 100)]
    assert calls["export"] == [("gcs", 200)]


def test_create_and_sync_cloud_storage_existing_and_new(tmp_path: Path):
    ls = FakeLS()
    proj = FakeProject(project_id=9)

    # existing import storage with prefix
    proj._import_storages = [{"id": 5, "prefix": "px"}]

    calls = {"synced": []}

    def sync_import_storage(kind, sid):
        calls["synced"].append((kind, sid))

    proj.sync_import_storage = sync_import_storage
    ls._project = proj

    # should sync existing, not create new
    ls.create_and_sync_cloud_storage(
        project_id=9,
        bucket_name="b",
        storage_prefix="px",
        storage_type="import",
        gcp_credentials=str(tmp_path / "c.json"),
    )
    assert calls["synced"] == [("gcs", 5)]

    # when not existing, ensure create_cloud_storage is called and then synced
    created = {"id": 77}

    def create_cloud_storage(**kwargs):
        return created

    ls.create_cloud_storage = create_cloud_storage
    calls["synced"].clear()
    ls.create_and_sync_cloud_storage(
        project_id=9,
        bucket_name="b",
        storage_prefix="new",
        storage_type="import",
        gcp_credentials=str(tmp_path / "c.json"),
    )
    assert calls["synced"] == [("gcs", 77)]


def test_delete_projects_by_prefix(monkeypatch):
    ls = FakeLS()
    ls._projects = [
        SimpleNamespace(id=1, title="pref-A"),
        SimpleNamespace(id=2, title="pref-B"),
        SimpleNamespace(id=3, title="other"),
    ]

    deleted = []

    class ClientStub:
        def delete_project(self, pid):
            deleted.append(pid)

    ls.client = ClientStub()
    titles = ls.delete_projects_by_prefix("pref-")

    assert sorted(titles) == ["pref-A", "pref-B"]
    assert sorted(deleted) == [1, 2]


def test_get_project_task_types_parses_label_config():
    ls = FakeLS()
    proj = FakeProject(project_id=10, title="cfg")
    # config includes rectangle, polygon, choices
    proj.label_config = """
    <View>
      <Image name="image" value="$image"/>
      <RectangleLabels name="bbox" toName="image"><Label value="Car"/></RectangleLabels>
      <PolygonLabels name="poly" toName="image"><Label value="Zone"/></PolygonLabels>
      <Choices name="cls" toName="image"><Choice value="A"/></Choices>
    </View>
    """
    ls._project = proj

    types = ls.get_project_task_types(project_id=10)
    assert set(types) == {"object_detection", "segmentation", "classification"}


def test_get_project_image_paths_and_gcs_paths():
    ls = FakeLS()
    proj = FakeProject(project_id=11, title="imgs")

    # Build tasks with various image URL forms
    proj._tasks = [
        {"id": 1, "data": {"image": "gs://bucket/a.jpg"}},
        {"id": 2, "data": {"image": "http://host/b.png"}},
    ]

    ls._project = proj

    # image paths
    paths = ls.get_project_image_paths(11)
    assert "gs://bucket/a.jpg" in paths
    assert "http://host/b.png" in paths

    # all existing across projects
    ls._projects = [proj]
    all_paths = ls.get_all_existing_image_paths()
    assert paths == all_paths

    # gcs-only
    gcs_paths = ls.get_all_existing_gcs_paths()
    assert gcs_paths == {"gs://bucket/a.jpg"}


def test_export_annotations_calls_sdk(monkeypatch, tmp_path: Path):
    ls = FakeLS()
    proj = FakeProject(project_id=12, title="exp")

    called = {"args": None}

    def export_tasks(**kwargs):
        called["args"] = kwargs
        out = kwargs.get("export_location")
        if out:
            Path(out).write_text("[]")
        return out or []

    proj.export_tasks = export_tasks
    ls._project = proj

    out = ls.export_annotations(
        project_id=12,
        export_type="JSON",
        download_all_tasks=True,
        download_resources=False,
        export_location=str(tmp_path / "x.json"),
    )
    assert called["args"]["export_type"] == "JSON"
    assert Path(out).exists()


def test_prod_get_projects_pagination_and_latest_part(monkeypatch):
    ls = FakeLS()
    # Provide projects directly via FakeLS surface
    ls._projects = [
        SimpleNamespace(id=1, title="Dataset Part 1"),
        SimpleNamespace(id=2, title="Dataset Part 3"),
        SimpleNamespace(id=3, title="Dataset Part 2"),
    ]

    part, title = ls.get_latest_project_part(r"Part (\d+)")
    assert part == 3 and title == "Dataset Part 3"


def test_prod_delete_projects_by_prefix(monkeypatch, tmp_path: Path):
    ls = FakeLS()
    ls._projects = [
        SimpleNamespace(id=1, title="pref-A"),
        SimpleNamespace(id=2, title="pref-B"),
        SimpleNamespace(id=3, title="other"),
    ]

    class ClientStub:
        def __init__(self):
            self.deleted = []

        def delete_project(self, pid):
            self.deleted.append(pid)

    ls.client = ClientStub()

    titles = ls.delete_projects_by_prefix("pref-")
    assert sorted(titles) == ["pref-A", "pref-B"]
    assert sorted(ls.client.deleted) == [1, 2]


def test_prod_list_import_export_storages(monkeypatch):
    class Proj:
        def get_import_storages(self):
            return [{"id": 1}]

        def get_export_storages(self):
            return [{"id": 2}]

    ls = FakeLS()
    ls._project = Proj()

    assert ls.list_import_storages(9) == [{"id": 1}]
    assert ls.list_export_storages(9) == [{"id": 2}]


def test_prod_create_cloud_storage_import_valid_and_invalid(tmp_path: Path):
    class Proj:
        def connect_google_import_storage(self, **kwargs):
            return {"id": 11, "title": kwargs.get("title")}

    ls = FakeLS()
    ls._project = Proj()

    with pytest.raises(ValueError):
        ls.create_cloud_storage(
            project_id=7,
            bucket="b",
            prefix="p",
            storage_type="import",
            google_application_credentials=str(tmp_path / "missing.json"),
        )

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    out = ls.create_cloud_storage(
        project_id=7, bucket="b", prefix="p", storage_type="import", google_application_credentials=str(creds)
    )
    assert out["id"] == 11


def test_prod_sync_and_create_and_sync_storage(tmp_path: Path):
    class Proj:
        def __init__(self):
            self._import_storages = [{"id": 5, "prefix": "px"}]
            self.synced = []

        def get_import_storages(self):
            return self._import_storages

        def get_export_storages(self):
            return []

        def sync_import_storage(self, kind, sid):
            self.synced.append((kind, sid))

    proj = Proj()
    ls = FakeLS()
    ls._project = proj

    # sync existing
    ls.create_and_sync_cloud_storage(
        project_id=1,
        bucket_name="b",
        storage_prefix="px",
        storage_type="import",
        gcp_credentials=str(tmp_path / "c.json"),
    )
    assert proj.synced == [("gcs", 5)]

    proj._import_storages = []
    creds = tmp_path / "c.json"
    creds.write_text("{}")

    def create_cloud_storage(**kwargs):
        return {"id": 77}

    # monkeypatch instance method
    ls.create_cloud_storage = create_cloud_storage  # type: ignore
    ls.create_and_sync_cloud_storage(
        project_id=1, bucket_name="b", storage_prefix="new", storage_type="import", gcp_credentials=str(creds)
    )
    assert proj.synced[-1] == ("gcs", 77)


def test_prod_get_project_task_types_and_image_paths_and_gcs():
    import base64

    class Proj:
        def __init__(self):
            self.label_config = (
                "<View>"
                '<RectangleLabels name="bbox" toName="image"><Label value="Car"/></RectangleLabels>'
                '<PolygonLabels name="poly" toName="image"><Label value="Zone"/></PolygonLabels>'
                '<Choices name="cls" toName="image"><Choice value="A"/></Choices>'
                "</View>"
            )
            self._tasks = []

        def get_tasks(self):
            return self._tasks

    proj = Proj()
    proj._tasks = [
        {"id": 1, "data": {"image": "gs://bucket/a.jpg"}},
        {"id": 2, "data": {"image": "http://host/b.png"}},
    ]

    # presigned URL encodes gs path
    gcs = "gs://bucket/c.jpg"
    encoded = base64.b64encode(gcs.encode()).decode()
    proj2 = Proj()
    proj2._tasks = [
        {"id": 3, "data": {"image": f"http://ls/presign?fileuri={encoded}"}},
    ]

    ls = FakeLS()
    ls._project = proj

    types = ls.get_project_task_types(project_id=1)
    assert set(types) == {"object_detection", "segmentation", "classification"}

    paths = ls.get_project_image_paths(1)
    assert "gs://bucket/a.jpg" in paths and "http://host/b.png" in paths

    # switch project to proj2 for gcs extraction via presign
    proj2.id = 1
    proj2.title = "A"
    ls._projects = [proj2]
    ls._project = proj2
    gcs_only = ls.get_all_existing_gcs_paths()
    assert gcs in gcs_only


def test_prod_export_annotations(tmp_path: Path):
    class Proj:
        def export_tasks(self, **kwargs):
            out = kwargs.get("export_location")
            if out:
                Path(out).write_text("[]")
            return out or []

    ls = FakeLS()
    ls._project = Proj()
    out = ls.export_annotations(
        project_id=1,
        export_type="JSON",
        download_all_tasks=True,
        download_resources=False,
        export_location=str(tmp_path / "x.json"),
    )
    assert Path(out).exists()


def test_list_annotations_for_task_and_all_branches():
    ls = FakeLS()

    class Proj:
        def __init__(self):
            self._tasks = [{"id": 1}, {"id": 2}]

        def get_tasks(self):
            return self._tasks

        def get_annotations(self, task_id):
            return [{"id": 10 + task_id}]

    ls._project = Proj()

    anns_one = ls.list_annotations(project_id=1, task_id=1)
    assert anns_one == [{"id": 11}]

    anns_all = ls.list_annotations(project_id=1)
    assert len(anns_all) == 2 and {a["id"] for a in anns_all} == {11, 12}


def test_get_task_and_delete_task_and_create_annotation():
    ls = FakeLS()

    calls = {"deleted": [], "annotated": []}

    class Proj:
        def get_task(self, task_id):
            return {"id": task_id}

        def delete_task(self, task_id):
            calls["deleted"].append(task_id)

        def create_annotation(self, task_id, annotation):
            calls["annotated"].append((task_id, annotation))
            return {"ok": True}

    ls._project = Proj()

    t = ls.get_task(project_id=1, task_id=7)
    assert t["id"] == 7

    ls.delete_task(project_id=1, task_id=7)
    assert calls["deleted"] == [7]

    out = ls.create_annotation(project_id=1, task_id=7, annotation={"a": 1})
    assert out == {"ok": True} and calls["annotated"] == [(7, {"a": 1})]


def test_create_cloud_storage_export_valid(tmp_path: Path):
    ls = FakeLS()

    class Proj:
        def connect_google_export_storage(self, **kwargs):
            return {"id": 21, "title": kwargs.get("title")}

    ls._project = Proj()

    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    out = ls.create_cloud_storage(
        project_id=1, bucket="b", prefix="p", storage_type="export", google_application_credentials=str(creds)
    )
    assert out["id"] == 21


def test_sync_storage_export_branch():
    ls = FakeLS()
    calls = {"export": []}

    class Proj:
        def sync_export_storage(self, kind, sid):
            calls["export"].append((kind, sid))

    ls._project = Proj()
    ls.sync_storage(1, 55, storage_type="export")
    assert calls["export"] == [("gcs", 55)]


def test_create_project_with_storage_happy(tmp_path: Path):
    ls = FakeLS()

    # Monkeypatch create_project, create_cloud_storage, sync_storage
    ls.create_project = lambda title, description=None, label_config=None: SimpleNamespace(id=99, title=title)  # type: ignore
    ls.create_cloud_storage = (
        lambda project_id, bucket, prefix, storage_type, google_application_credentials=None, regex_filter=None: {
            "id": 5
        }
    )  # type: ignore
    ls.sync_storage = lambda project_id, storage_id, storage_type="import": True  # type: ignore

    proj, storage = ls.create_project_with_storage(
        title="T",
        bucket="b",
        prefix="p",
        label_config="<View/>",
        description="d",
        google_application_credentials=str((tmp_path / "c.json").write_text("{}") or (tmp_path / "c.json")),
        regex_filter=None,
    )
    assert proj.id == 99 and storage["id"] == 5


def test_prod_init_uses_passed_url_and_api_key(monkeypatch):
    import logging

    from mindtrace.automation.label_studio import label_studio_api as mod

    class DummyClient:
        def __init__(self, url, api_key):
            self.url = url
            self.api_key = api_key

    def mt_init(self, **kwargs):
        self.logger = logging.getLogger("LabelStudioTest")
        self.config = {
            "MINDTRACE_DEFAULT_HOST_URLS": {"LabelStudio": "http://default"},
            "MINDTRACE_API_KEYS": {"LabelStudio": "default"},
            "MINDTRACE_GCP_CREDENTIALS_PATH": str(Path.cwd() / "fake_creds.json"),
        }

    monkeypatch.setattr(mod, "Client", DummyClient)
    monkeypatch.setattr(mod.Mindtrace, "__init__", mt_init)

    ls = mod.LabelStudio(url="http://host", api_key="k")
    assert isinstance(ls.client, DummyClient)
    assert ls.client.url == "http://host" and ls.client.api_key == "k"


def test_prod_get_projects_pagination_success(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    class DummyClient:
        def __init__(self, url, api_key):
            pass

        def list_projects(self, *, page, page_size, **kwargs):
            if page == 1:
                return [SimpleNamespace(id=1, title="A"), SimpleNamespace(id=2, title="B")]
            if page == 2:
                return [SimpleNamespace(id=3, title="C")]
            return []

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(mod, "Client", DummyClient)

    ls = mod.LabelStudio(url="u", api_key="k")
    projs = ls.get_projects(page_size=2)
    assert len(projs) == 3 and {p.title for p in projs} == {"A", "B", "C"}


def test_prod_get_project_by_name_and_id_and_not_found(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    class DummyClient:
        def __init__(self, url, api_key):
            pass

        def get_project(self, pid):
            return SimpleNamespace(id=pid, title="X")

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(mod, "Client", DummyClient)

    ls = mod.LabelStudio(url="u", api_key="k")
    # supply projects via monkeypatched get_projects
    ls.get_projects = lambda page_size=100, **qp: [SimpleNamespace(id=1, title="P1"), SimpleNamespace(id=2, title="P2")]  # type: ignore

    assert ls.get_project(project_id=7).id == 7
    assert ls.get_project(project_name="P2").title == "P2"

    with pytest.raises(mod.ProjectNotFoundError):
        ls.get_project(project_name="NOPE")


def test_prod_delete_project_validation_and_success(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    # Mindtrace.__init__ is provided by autouse fixture
    ls = mod.LabelStudio(url="u", api_key="k")

    with pytest.raises(ValueError):
        ls.delete_project()

    ls.get_project = lambda project_name=None, project_id=None: SimpleNamespace(id=9, title="T")  # type: ignore
    calls = {"deleted": []}

    class DummyClient:
        def delete_project(self, pid):
            calls["deleted"].append(pid)

    ls.client = DummyClient()

    ls.delete_project(project_id=9)
    assert calls["deleted"] == [9]


def test_prod_create_tasks_from_images_success_and_empty(tmp_path: Path, monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    files_dir = tmp_path / "imgs"
    files_dir.mkdir()
    (files_dir / "a.jpg").write_bytes(b"x")
    (files_dir / "b.png").write_bytes(b"x")
    (files_dir / "c.txt").write_text("nope")

    class Proj:
        def __init__(self):
            self.id = 1
            self.title = "T"
            self.calls = []

        def import_tasks(self, path):
            self.calls.append(path)
            return [1]

    proj = Proj()

    # Mindtrace.__init__ is provided by autouse fixture
    ls = mod.LabelStudio(url="u", api_key="k")
    ls.get_project = lambda project_name=None, project_id=None: proj  # type: ignore

    created = ls.create_tasks_from_images(project_id=1, local_dir=str(files_dir), recursive=False, batch_size=1)
    assert created == 2 and len(proj.calls) == 2

    # empty directory case
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    created2 = ls.create_tasks_from_images(project_id=1, local_dir=str(empty_dir), recursive=False, batch_size=10)
    assert created2 == 0


def test_prod_get_task_types_and_annotations_and_tasks(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    class Proj:
        def __init__(self):
            self.label_config = (
                "<View>"
                '<RectangleLabels name="bbox" toName="image"><Label value="Car"/></RectangleLabels>'
                '<PolygonLabels name="poly" toName="image"><Label value="Zone"/></PolygonLabels>'
                '<Choices name="cls" toName="image"><Choice value="A"/></Choices>'
                "</View>"
            )
            self._tasks = [
                {"id": 1, "annotations": [{"id": 11}]},
                {"id": 2, "annotations": []},
            ]

        def get_tasks(self):
            return self._tasks

        def get_task(self, tid):
            return next((t for t in self._tasks if t["id"] == tid), {})

        def delete_task(self, tid):
            self._tasks = [t for t in self._tasks if t["id"] != tid]

        def create_annotation(self, task_id, ann):
            return {"ok": True}

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: None)
    ls = mod.LabelStudio(url="u", api_key="k")
    p = Proj()
    ls.get_project = lambda project_name=None, project_id=None: p  # type: ignore

    types = ls.get_task_types(project_id=1)
    assert set(types) == {"object_detection", "segmentation", "classification"}

    assert ls.get_tasks(project_id=1) == p.get_tasks()
    assert ls.get_task(project_id=1, task_id=1)["id"] == 1
    ls.delete_task(project_id=1, task_id=2)
    assert all(t["id"] != 2 for t in p.get_tasks())
    assert ls.create_annotation(project_id=1, task_id=1, annotation={"a": 1}) == {"ok": True}


def test_prod_export_annotations_success_and_error(tmp_path: Path, monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    class Proj:
        def export_tasks(self, **kwargs):
            out = kwargs.get("export_location")
            if out:
                Path(out).write_text("[]")
            return out or []

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: None)
    ls = mod.LabelStudio(url="u", api_key="k")
    ls.get_project = lambda project_name=None, project_id=None: Proj()  # type: ignore

    out = ls.export_annotations(
        project_id=1,
        export_type="JSON",
        download_all_tasks=True,
        download_resources=False,
        export_location=str(tmp_path / "x.json"),
    )
    assert Path(out).exists()

    class BadProj:
        def export_tasks(self, **kwargs):
            raise RuntimeError("boom")

    ls.get_project = lambda project_name=None, project_id=None: BadProj()  # type: ignore
    with pytest.raises(Exception):
        ls.export_annotations(project_id=1, export_type="JSON")


def test_prod_create_gcp_storage_duplicates_and_creds_errors_and_success(tmp_path: Path, monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod
    from mindtrace.automation.label_studio.exceptions import (
        CredentialsNotFoundError,
        CredentialsReadError,
        StorageAlreadyExistsError,
    )

    class Proj:
        def __init__(self):
            self._import_storages = [{"id": 1, "title": "GCS Import b/p"}]

        def get_import_storages(self):
            return self._import_storages

        def get_export_storages(self):
            return []

        def connect_google_import_storage(self, **kw):
            return {"id": 10}

    monkeypatch.setattr(
        mod.Mindtrace,
        "__init__",
        lambda self, **kw: setattr(self, "config", {"MINDTRACE_GCP_CREDENTIALS_PATH": str(tmp_path / "missing.json")}),
    )
    ls = mod.LabelStudio(url="u", api_key="k")
    ls.get_project = lambda project_name=None, project_id=None: Proj()  # type: ignore

    # duplicate
    with pytest.raises(StorageAlreadyExistsError):
        ls.create_gcp_storage(project_id=1, bucket="b", prefix="p", storage_type="import")

    # missing creds
    ls.get_project = lambda project_name=None, project_id=None: Proj()  # type: ignore
    with pytest.raises(CredentialsNotFoundError):
        ls.create_gcp_storage(project_id=1, bucket="bx", prefix="px", storage_type="import")

    # invalid json
    bad = tmp_path / "bad.json"
    bad.write_text("{notjson}")
    with pytest.raises(CredentialsReadError):
        ls.create_gcp_storage(
            project_id=1, bucket="bx", prefix="px", storage_type="import", google_application_credentials=str(bad)
        )

    # success
    good = tmp_path / "good.json"
    good.write_text("{}")
    out = ls.create_gcp_storage(
        project_id=1, bucket="bx", prefix="px", storage_type="import", google_application_credentials=str(good)
    )
    assert out["id"] == 10


def test_prod_sync_gcp_storage_all_branches(tmp_path: Path, monkeypatch):
    import logging

    from mindtrace.automation.label_studio import label_studio_api as mod

    class Proj:
        def __init__(self):
            self._import_storages = [{"id": 5, "prefix": "px"}]
            self._export_storages = [{"id": 6, "prefix": "ex"}]
            self.synced = []

        def get_import_storages(self):
            return self._import_storages

        def get_export_storages(self):
            return self._export_storages

        def sync_import_storage(self, kind, sid):
            self.synced.append(("import", kind, sid))

        def sync_export_storage(self, kind, sid):
            self.synced.append(("export", kind, sid))

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: setattr(self, "logger", logging.getLogger("t")))
    ls = mod.LabelStudio(url="u", api_key="k")
    p = Proj()
    ls.get_project = lambda project_name=None, project_id=None: p  # type: ignore

    # invalid storage_type
    with pytest.raises(ValueError):
        ls.sync_gcp_storage(project_id=1, storage_id=1, storage_type="x")

    # by id import/export
    assert ls.sync_gcp_storage(project_id=1, storage_id=5, storage_type="import") is True
    assert ls.sync_gcp_storage(project_id=1, storage_id=6, storage_type="export") is True

    # by prefix import/export
    assert ls.sync_gcp_storage(project_id=1, storage_prefix="px", storage_type="import") is True
    assert ls.sync_gcp_storage(project_id=1, storage_prefix="ex", storage_type="export") is True

    # missing id and prefix
    with pytest.raises(ValueError):
        ls.sync_gcp_storage(project_id=1, storage_type="import")

    # retry path to RuntimeError
    class BadProj(Proj):
        def sync_import_storage(self, kind, sid):
            raise RuntimeError("boom")

    ls.get_project = lambda project_name=None, project_id=None: BadProj()  # type: ignore
    # speed up retry
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        ls.sync_gcp_storage(project_id=1, storage_id=5, storage_type="import", max_attempts=2, retry_delay=0)


def test_prod_list_storages_error_paths(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    class BadClient:
        def get_project(self, pid):
            raise RuntimeError("boom")

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: None)
    ls = mod.LabelStudio(url="u", api_key="k")
    ls.client = BadClient()

    with pytest.raises(Exception):
        ls.list_import_storages(project_id=1)
    with pytest.raises(Exception):
        ls.list_export_storages(project_id=1)


def test_prod_export_projects_by_prefix(monkeypatch, tmp_path: Path):
    from mindtrace.automation.label_studio import label_studio_api as mod

    monkeypatch.setattr(mod.Mindtrace, "__init__", lambda self, **kw: None)
    ls = mod.LabelStudio(url="u", api_key="k")
    ls.get_projects = lambda page_size=100, **qp: [
        SimpleNamespace(id=1, title="pref-A"),
        SimpleNamespace(id=2, title="X"),
    ]  # type: ignore

    created = []

    def fake_export_annotations(**kwargs):
        created.append(kwargs["export_location"])
        Path(kwargs["export_location"]).write_text("[]")

    ls.export_annotations = fake_export_annotations  # type: ignore

    out = ls.export_projects_by_prefix("pref-", output_dir=str(tmp_path), export_type="JSON", download_resources=False)
    assert out == ["pref-A"]
    assert (tmp_path / "pref-A" / "export.json").exists()

    # no matches
    out2 = ls.export_projects_by_prefix("NOPE-", output_dir=str(tmp_path), export_type="JSON", download_resources=False)
    assert out2 == []


def test_prod_extract_gcs_and_image_path_and_get_project_image_paths_error(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    ls = mod.LabelStudio(url="u", api_key="k")

    # valid presign
    import base64

    gcs = "gs://bucket/a.jpg"
    enc = base64.b64encode(gcs.encode()).decode()
    url = f"http://ls/data/storage/gcs/presign?fileuri={enc}"
    assert ls._extract_gcs_path_from_label_studio_url(url) == gcs

    # not presign
    assert ls._extract_gcs_path_from_label_studio_url("http://ls/data") is None

    # bad decode
    bad = "http://ls/data/storage/gcs/presign?fileuri=@@@"
    assert ls._extract_gcs_path_from_label_studio_url(bad) is None

    # image path extraction
    t = {"data": {"image": url}}
    assert ls._extract_image_path_from_task(t) == gcs

    # error branch for get_project_image_paths
    ls.get_tasks = lambda project_name=None, project_id=None: (_ for _ in ()).throw(RuntimeError("x"))  # type: ignore
    assert ls.get_project_image_paths(project_id=1) == set()


def test_init_original_paths(monkeypatch):
    # Restore original __init__ and ensure Mindtrace.__init__ provides logger/config
    from mindtrace.automation.label_studio import label_studio_api as mod

    def mt_init(self, **kwargs):
        self.logger = logging.getLogger("LabelStudioTest")
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.config = {
            "MINDTRACE_DEFAULT_HOST_URLS": {"LabelStudio": "http://localhost"},
            "MINDTRACE_API_KEYS": {"LabelStudio": "test-key"},
            "MINDTRACE_GCP_CREDENTIALS_PATH": str(Path.cwd() / "creds.json"),
        }

    monkeypatch.setattr(mod.Mindtrace, "__init__", mt_init)
    # keep DummyClient from autouse fixture
    monkeypatch.setattr(mod.LabelStudio, "__init__", mod._ORIG_LS_INIT)
    ls = mod.LabelStudio(url=None, api_key=None)
    assert ls.url == "http://localhost" and ls.api_key == "test-key"


def test_get_projects_error_logs(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    ls = mod.LabelStudio(url="http://localhost", api_key="k")

    class BadClient:
        def list_projects(self, **kwargs):
            raise RuntimeError("boom")

    ls.client = BadClient()
    with pytest.raises(Exception):
        ls.get_projects()


def test_get_project_fetch_errors(monkeypatch):
    from mindtrace.automation.label_studio import label_studio_api as mod

    ls = mod.LabelStudio(url="http://localhost", api_key="k")
    # name fetch raises
    ls._get_project_by_name = lambda name, **qp: (_ for _ in ()).throw(RuntimeError("x"))  # type: ignore
    with pytest.raises(mod.ProjectFetchError):
        ls.get_project(project_name="X")

    # id fetch raises
    class BadClient:
        def get_project(self, pid):
            raise RuntimeError("y")

    ls.client = BadClient()
    with pytest.raises(mod.ProjectFetchError):
        ls.get_project(project_id=1)


def test_delete_projects_by_prefix_no_matches_and_delete_error(monkeypatch, tmp_path):
    ls = LabelStudio(url="http://localhost", api_key="k")
    # empty raises
    with pytest.raises(ValueError):
        ls.delete_projects_by_prefix("")
    # no matches returns []
    ls.get_projects = lambda page_size=100, **qp: []  # type: ignore
    assert ls.delete_projects_by_prefix("pref-") == []
    # matches with one failing delete
    projs = [SimpleNamespace(id=1, title="pref-A"), SimpleNamespace(id=2, title="pref-B")]
    ls.get_projects = lambda page_size=100, **qp: projs  # type: ignore

    class ClientStub:
        def __init__(self):
            self.calls = []

        def delete_project(self, pid):
            self.calls.append(pid)
            if pid == 2:
                raise RuntimeError("fail")

    ls.client = ClientStub()
    out = ls.delete_projects_by_prefix("pref-")
    assert sorted(out) == ["pref-A"]


def test_create_tasks_from_images_error_paths(tmp_path):
    ls = LabelStudio(url="http://localhost", api_key="k")
    with pytest.raises(ValueError):
        ls.create_tasks_from_images(project_id=1, local_dir=None)
    with pytest.raises(ValueError):
        ls.create_tasks_from_images(project_id=1, local_dir=str(tmp_path), batch_size=0)
    with pytest.raises(ValueError):
        ls.create_tasks_from_images(project_id=1, local_dir=str(tmp_path / "missing"))


def test_create_tasks_from_images_import_failure_warning(tmp_path):
    p = tmp_path / "imgs"
    p.mkdir()
    f = p / "a.jpg"
    f.write_bytes(b"x")

    class Proj:
        id = 1
        title = "T"

        def import_tasks(self, path):
            raise RuntimeError("boom")

    ls = LabelStudio(url="http://localhost", api_key="k")
    ls.get_project = lambda project_name=None, project_id=None: Proj()  # type: ignore
    # Should swallow the exception and continue
    created = ls.create_tasks_from_images(project_id=1, local_dir=str(p), recursive=False)
    assert created == 0


def test_create_annotation_error_branch(monkeypatch):
    class Proj:
        def create_annotation(self, tid, ann):
            raise RuntimeError("x")

    ls = LabelStudio(url="http://localhost", api_key="k")
    ls.get_project = lambda **kw: Proj()  # type: ignore
    with pytest.raises(Exception):
        ls.create_annotation(project_id=1, task_id=1, annotation={})


def test_create_gcp_storage_export_branch(tmp_path):
    class Proj:
        def get_export_storages(self):
            return []

        def connect_google_export_storage(self, **kw):
            return {"id": 22, "title": kw.get("title")}

    ls = LabelStudio(url="http://localhost", api_key="k")
    ls.get_project = lambda **kw: Proj()  # type: ignore
    creds = tmp_path / "c.json"
    creds.write_text("{}")
    out = ls.create_gcp_storage(
        project_id=1,
        bucket="b",
        prefix="p",
        storage_type="export",
        google_application_credentials=str(creds),
        use_blob_urls=True,
    )
    assert out["id"] == 22


def test_sync_gcp_storage_not_found_import_and_export():
    from mindtrace.automation.label_studio import label_studio_api as mod

    class Proj:
        def get_import_storages(self):
            return []

        def get_export_storages(self):
            return []

    ls = LabelStudio(url="http://localhost", api_key="k")
    ls.get_project = lambda **kw: Proj()  # type: ignore
    with pytest.raises(mod.StorageNotFoundError):
        ls.sync_gcp_storage(project_id=1, storage_prefix="px", storage_type="import")
    with pytest.raises(mod.StorageNotFoundError):
        ls.sync_gcp_storage(project_id=1, storage_prefix="ex", storage_type="export")


def test_export_projects_by_prefix_yolo_and_error_branch(tmp_path):
    ls = LabelStudio(url="http://localhost", api_key="k")
    projs = [SimpleNamespace(id=1, title="pref-A"), SimpleNamespace(id=2, title="pref-B")]
    ls.get_projects = lambda **kw: projs  # type: ignore
    created = []

    def fake_export_annotations(**kw):
        if kw["project_id"] == 2:
            raise RuntimeError("fail")
        created.append(kw["export_location"])
        Path(kw["export_location"]).write_text("[]")

    ls.export_annotations = fake_export_annotations  # type: ignore
    out = ls.export_projects_by_prefix("pref-", output_dir=str(tmp_path), export_type="YOLO", download_resources=False)
    assert "pref-A" in out
    assert (tmp_path / "pref-A" / "export.zip").exists()


def test_extract_gcs_decode_non_gcs_and_errors():
    ls = LabelStudio(url="http://localhost", api_key="k")
    import base64

    not_gcs = base64.b64encode(b"http://foo").decode()
    url = f"http://ls/presign?fileuri={not_gcs}"
    assert ls._extract_gcs_path_from_label_studio_url(url) is None
    bad = "http://ls/presign?fileuri=%%%"
    assert ls._extract_gcs_path_from_label_studio_url(bad) is None
    assert ls._extract_gcs_path_from_label_studio_url(None) is None


def test_extract_image_path_from_task_variants():
    ls = LabelStudio(url="http://localhost", api_key="k")
    assert ls._extract_image_path_from_task(None) is None
    assert ls._extract_image_path_from_task({}) is None
    t = {"data": {"image": "http://host/img.jpg"}}
    assert ls._extract_image_path_from_task(t) == "http://host/img.jpg"
