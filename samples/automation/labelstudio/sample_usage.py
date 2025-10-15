from pathlib import Path

from mindtrace.automation.label_studio.label_studio_api import LabelStudio
from mindtrace.automation.label_studio.exceptions import ProjectAlreadyExistsError, StorageAlreadyExistsError
from mindtrace.core.config import Config

url = "http://localhost:8080"
config = Config()
api_key = config["MINDTRACE_API_KEYS"]["LabelStudio"]
google_application_credentials = config["MINDTRACE_GCP_CREDENTIALS_PATH"]

label_config = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="Cat" background="green"/>
    <Label value="Apple" background="blue"/>
  </RectangleLabels>
</View>
"""
ls = LabelStudio(url=url, api_key=api_key)

# 1. Create project (raises if it already exists)
try:
    project = ls.create_project(project_name="test_project", description="Test project", label_config=label_config)
except ProjectAlreadyExistsError:
    pass

# 2. Import tasks from local directory
project = ls.get_project(project_name="test_project")
sample_dir = str((Path(__file__).parent / "sample_images").resolve())
created = ls.create_tasks_from_images(project_name="test_project", local_dir=sample_dir)
print(f"Created {created} tasks in project '{project.title}' (ID: {project.id})")

# 3. Import tasks from GCP cloud storage

# 3.1 Create GCP storage
try:
    storage = ls.create_gcp_storage(
        project_name="test_project",
        bucket="mt-label-studio-bucket",
        prefix="samples",
        storage_type="import",
        use_blob_urls=True,
        presign=False,
        google_application_credentials=google_application_credentials,
        regex_filter=".*jpg",
    )
    print(f"Created GCP storage id: {storage['id']} in project '{project.title}' (ID: {project.id})")
except StorageAlreadyExistsError:
    print(f"GCP storage already exists in project '{project.title}' (ID: {project.id})")

# 3.2 Sync GCP storage
sync_gcp_storage = ls.sync_gcp_storage(project_name="test_project", storage_prefix="samples")
print(f"Synced GCP storage in project '{project.title}' (ID: {project.id})")

# 4. Get annotations
annotations = ls.get_annotations(project_name="test_project")
for annotation in annotations:
    for key, value in annotation.items():
        print(f"{key}:{value}")
    print("--------------------------------")
