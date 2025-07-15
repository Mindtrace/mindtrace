from label_studio_sdk import Client
import os
from typing import Optional, Union, Any
from pathlib import Path
import re
import json
from dataclasses import dataclass
from mindtrace.core import Mindtrace


@dataclass
class LabelStudioConfig:
    """Configuration for Label Studio project."""

    url: str
    api_key: str
    gcp_creds: Optional[Union[str, dict]] = None
    default_label_config: Optional[str] = None


class LabelStudio(Mindtrace):
    """
    Features:
    - Simplified project and task management
    - Automatic retry mechanisms
    - Progress tracking for long operations
    - Flexible configuration management

    Example:
        config = LabelStudioConfig(
            url="your_url",
            api_key="your_key",
            gcp_creds="path_to_creds.json"
        )

        label_studio = LabelStudio(config)

        project = label_studio.create_project(
            title="Traffic Analysis",
            description="Analysing traffic patterns",
            label_config='''
                <View>
                    <Image name="image" value="$image"/>
                    <RectangleLabels name="label" toName="image">
                        <Label value="Car" background="#ff0000"/>
                        <Label value="Person" background="#00ff00"/>
                    </RectangleLabels>
                </View>
            '''
        )

        tasks = [{"image": "url1"}, {"image": "url2"}]
        project.create_tasks(tasks)

        label_studio.export_annotations(
            project_id=project.id,
            export_type="YOLO",
            export_location="output_dir/export.zip"
        )
    """

    def __init__(self, config: LabelStudioConfig, **kwargs):
        """Initialise with configuration object."""
        super().__init__(**kwargs)
        self.config = config
        self.logger.info(f"Initialising Label Studio client with URL: {config.url}")
        self.client = Client(url=config.url, api_key=config.api_key)

    def list_projects(self) -> list:
        """Retrieve all projects."""
        return self.client.get_projects()

    def get_project(self, project_id: int):
        """Retrieve a specific project by ID."""
        return self.client.get_project(project_id)

    def get_project_by_name(self, project_name: str) -> Optional[int]:
        """Retrieve project ID by exact name match."""
        projects = self.list_projects()
        matching = [p for p in projects if p.title == project_name]
        if len(matching) > 1:
            self.logger.error(f"Multiple projects found with name '{project_name}'")
            raise ValueError(f"Multiple projects found with name '{project_name}'")
        return matching[0] if matching else None

    def create_project(self, title: str, description: str = "", label_config: str = "") -> dict:
        """Create a new project.

        Args:
            title: Project name
            description: Project description
            label_config: Label configuration in XML format
        """
        return self.client.create_project(title=title, description=description, label_config=label_config)

    def delete_project(self, project_id: Optional[int] = None, project_name: Optional[str] = None) -> None:
        """Delete a project by ID or name.

        Args:
            project_id: Project ID to delete
            project_name: Project name to delete

        Raises:
            ValueError: If neither project_id nor project_name is provided,
                      or if project with given name is not found
        """
        if not (project_id or project_name):
            raise ValueError("Must provide either project_id or project_name")

        if project_name:
            project = self.get_project_by_name(project_name)
            if not project:
                raise ValueError(f"No project found with name: {project_name}")
            project_id = project.id

        self.logger.info(f"Deleting project with ID: {project_id}")
        self.client.delete_project(project_id)
        self.logger.info("Project deleted successfully")

    def get_latest_project_part(self, pattern: str) -> tuple[Optional[int], Optional[str]]:
        """Find latest project part number matching pattern."""
        projects = self.list_projects()
        part_numbers = []
        for project in projects:
            match = re.search(pattern, project.title)
            if match:
                part_numbers.append((int(match.group(1)), project.title))
        if part_numbers:
            return max(part_numbers, key=lambda x: x[0])
        return None, None

    def list_tasks(self, project_id: int) -> list:
        """Get all tasks in a project."""
        return self.get_project(project_id).get_tasks()

    def get_task(self, project_id: int, task_id: int) -> dict:
        """Get a specific task."""
        return self.get_project(project_id).get_task(task_id)

    def delete_task(self, project_id: int, task_id: int) -> None:
        """Delete a task."""
        self.get_project(project_id).delete_task(task_id)

    def list_annotations(self, project_id: int, task_id: Optional[int] = None) -> list:
        """Get annotations for a task or all tasks."""
        project = self.get_project(project_id)
        return project.get_annotations(task_id) if task_id else project.get_annotations()

    def create_annotation(self, project_id: int, task_id: int, annotation: dict) -> dict:
        """Create an annotation for a task."""
        return self.get_project(project_id).create_annotation(task_id, annotation)

    def export_annotations(
        self,
        project_id: int,
        export_type: str = "YOLO",
        download_all_tasks: bool = True,
        download_resources: bool = True,
        ids: list = None,
        export_location: str = None,
    ) -> Union[list, Path]:
        """
        Export project annotations in various formats.

        Args:
            project_id: ID of the project
            export_type: Format ('YOLO', 'JSON', 'CSV', etc.)
            download_all_tasks: Include unannotated tasks
            download_resources: Download images/resources
            ids: List of task IDs to export
            export_location: Path to save export (required for file output)

        Returns:
            List of annotations or Path to export file
        """
        project = self.get_project(project_id)
        self.logger.info(f"Exporting project {project_id} in {export_type} format")
        return project.export_tasks(
            export_type=export_type,
            download_all_tasks=download_all_tasks,
            download_resources=download_resources,
            ids=ids,
            export_location=export_location,
        )

    def create_cloud_storage(
        self,
        project_id: int,
        bucket: str,
        prefix: Optional[str] = None,
        storage_type: str = "import",
        google_application_credentials: Optional[str] = None,
        regex_filter: Optional[str] = None,
    ) -> dict:
        """Create Google Cloud Storage for import or export.

        Args:
            project_id: Target project ID
            bucket: GCS bucket name
            prefix: Optional path prefix in bucket
            storage_type: Either "import" or "export"
            google_application_credentials: Path to credentials JSON file
            regex_filter: Regex filter for matching image types

        Returns:
            Created storage details

        Raises:
            ValueError: If credentials file is missing or invalid
            requests.exceptions.RequestException: If API request fails
            json.JSONDecodeError: If credentials file contains invalid JSON
            OSError: If there are file system errors
        """
        project = self.get_project(project_id)
        storage_name = (
            f"GCS {storage_type.title()} {bucket}/{prefix}" if prefix else f"GCS {storage_type.title()} {bucket}"
        )

        if not google_application_credentials or not os.path.exists(google_application_credentials):
            raise ValueError(f"GCP credentials file not found at: {google_application_credentials}")

        try:
            with open(google_application_credentials, "r") as f:
                credentials_content = f.read()
                json.loads(credentials_content)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Error reading credentials file: {str(e)}")

        self.logger.info(f"Creating {storage_type} storage: {storage_name}")
        self.logger.debug(f"Using bucket: {bucket}, prefix: {prefix}")

        try:
            if storage_type == "import":
                return project.connect_google_import_storage(
                    bucket=bucket,
                    prefix=prefix,
                    regex_filter=regex_filter,
                    use_blob_urls=False,
                    presign=True,
                    presign_ttl=1,
                    title=storage_name,
                    description="Imported via Label Studio SDK",
                    google_application_credentials=credentials_content,
                )
            else:
                return project.connect_google_export_storage(
                    bucket=bucket,
                    prefix=prefix,
                    use_blob_urls=False,
                    title=storage_name,
                    description="Exported via Label Studio SDK",
                    google_application_credentials=credentials_content,
                )
        except Exception as e:
            self.logger.error(f"Failed to create storage: {str(e)}")
            raise

    def sync_storage(
        self, project_id: int, storage_id: int, storage_type: str = "import", max_attempts: int = 100
    ) -> bool:
        """Synchronise Google Cloud Storage.

        Args:
            project_id: Project ID
            storage_id: Storage ID to sync
            storage_type: Either "import" or "export"
            max_attempts: Maximum sync attempts

        Returns:
            True if sync successful

        Raises:
            ValueError: If storage_type invalid
            TimeoutError: If sync times out
        """
        project = self.get_project(project_id)

        self.logger.info(f"Starting {storage_type} storage sync for storage ID: {storage_id}")
        if storage_type == "import":
            project.sync_import_storage("gcs", storage_id)
        else:
            project.sync_export_storage("gcs", storage_id)

    def create_and_sync_cloud_storage(
        self,
        project_id: int,
        bucket_name: str,
        storage_prefix: str,
        storage_type: str = "export",
        gcp_credentials=None,
        regex_filter: Optional[str] = None,
    ) -> bool:
        """Create and synchronise Google Cloud Storage.

        This is a convenience method that combines create_cloud_storage and sync_storage.
        If storage with the given prefix exists, it will only sync that storage.
        If no storage exists with the prefix, it will create one and then sync it.

        Args:
            project_id: Target project ID
            bucket_name: GCS bucket name
            storage_prefix: Storage prefix/path
            storage_type: Either "import" or "export"
            gcp_credentials: Optional override credentials
            regex_filter: Regex filter for matching image types

        Returns:
            True if sync successful
        """
        project = self.get_project(project_id)

        if storage_type == "import":
            storages = project.get_import_storages()
        else:
            storages = project.get_export_storages()

        for storage in storages:
            if storage["prefix"] == storage_prefix:
                self.logger.info(f"Found existing storage with prefix {storage_prefix}")
                return self.sync_storage(project_id, storage["id"], storage_type)

        self.logger.info(f"Creating new {storage_type} storage for prefix {storage_prefix}")
        storage = self.create_cloud_storage(
            project_id=project_id,
            bucket=bucket_name,
            prefix=storage_prefix,
            storage_type=storage_type,
            google_application_credentials=gcp_credentials,
            regex_filter=regex_filter,
        )

        return self.sync_storage(project_id, storage["id"], storage_type)

    def create_project_with_storage(
        self,
        title: str,
        bucket: str,
        prefix: str,
        label_config: str,
        description: str = None,
        google_application_credentials: Optional[str] = None,
        regex_filter: Optional[str] = None,
    ) -> tuple[Any, Any]:
        """Create a project and set up Google Cloud Storage import in one operation.

        Args:
            title: Project name
            bucket: GCS bucket name
            prefix: Storage prefix/path
            label_config: Label configuration in XML format
            description: Optional project description
            google_application_credentials: Optional path to GCP credentials
            regex_filter: Regex filter for matching image types

        Returns:
            Tuple of (project, storage) objects
        """
        self.logger.info(f"Creating new project: {title}")
        project = self.create_project(title=title, description=description, label_config=label_config)

        self.logger.info(f"Setting up import storage for project {project.id}")
        storage = self.create_cloud_storage(
            project_id=project.id,
            bucket=bucket,
            prefix=prefix,
            storage_type="import",
            google_application_credentials=google_application_credentials,
            regex_filter=regex_filter,
        )

        self.logger.info(f"Syncing storage for project {project.id}")
        self.sync_storage(project.id, storage["id"], storage_type="import")

        return project, storage

    def delete_projects_by_prefix(self, title_prefix: str) -> list[str]:
        """Delete all projects whose titles start with the specified prefix.

        Args:
            title_prefix: The prefix to match against project titles

        Returns:
            List of deleted project titles

        Raises:
            ValueError: If title_prefix is empty
        """
        if not title_prefix:
            raise ValueError("title_prefix cannot be empty")

        self.logger.info(f"Finding projects with title prefix: {title_prefix}")
        projects = self.list_projects()
        matching_projects = [p for p in projects if p.title.startswith(title_prefix)]

        if not matching_projects:
            self.logger.info(f"No projects found with title prefix: {title_prefix}")
            return []

        deleted_titles = []
        for project in matching_projects:
            try:
                self.logger.info(f"Deleting project: {project.title} (ID: {project.id})")
                self.client.delete_project(project.id)
                deleted_titles.append(project.title)
            except Exception as e:
                self.logger.error(f"Failed to delete project {project.title}: {str(e)}")

        self.logger.info(f"Deleted {len(deleted_titles)} projects")
        return deleted_titles

    def export_projects_by_prefix(
        self,
        title_prefix: str,
        output_dir: str = "./export_output",
        export_type: str = "YOLO",
        download_resources: bool = True,
        show_progress: bool = True,
    ) -> list[str]:
        """Export all projects whose titles start with the specified prefix.

        Args:
            title_prefix: The prefix to match against project titles
            output_dir: Base directory for exports
            export_type: Format to export in ('YOLO', 'JSON', 'CSV', etc.)
            download_resources: Whether to download images/resources
            show_progress: Whether to show progress bar

        Returns:
            List of exported project titles

        Raises:
            ValueError: If title_prefix is empty
        """
        if not title_prefix:
            raise ValueError("title_prefix cannot be empty")

        self.logger.info(f"Finding projects with title prefix: {title_prefix}")
        projects = self.list_projects()
        matching_projects = [p for p in projects if p.title.startswith(title_prefix)]

        if not matching_projects:
            self.logger.info(f"No projects found with title prefix: {title_prefix}")
            return []

        exported_titles = []
        for project in matching_projects:
            try:
                project_dir = os.path.join(output_dir, f"{project.title}")
                os.makedirs(project_dir, exist_ok=True)

                self.logger.info(f"Exporting project: {project.title} (ID: {project.id})")
                export_file = os.path.join(project_dir, f"export.{export_type.lower()}")
                if export_type.upper() in ["YOLO", "COCO"]:
                    export_file = os.path.join(project_dir, "export.zip")

                self.export_annotations(
                    project_id=project.id,
                    export_type=export_type,
                    download_resources=download_resources,
                    export_location=export_file,
                )
                exported_titles.append(project.title)
            except Exception as e:
                self.logger.error(f"Failed to export project {project.title}: {str(e)}")

        self.logger.info(f"Exported {len(exported_titles)} projects")
        return exported_titles

    def get_project_task_types(self, project_id: Optional[int] = None, project_name: Optional[str] = None) -> list[str]:
        """Determine the task types in a project by analyzing its label configuration.

        Args:
            project_id: Project ID to analyze
            project_name: Project name to analyze

        Returns:
            List of task types found in the project (e.g., ['object_detection', 'classification', 'segmentation'])

        Raises:
            ValueError: If neither project_id nor project_name is provided,
                      or if project with given name is not found
        """
        if not (project_id or project_name):
            raise ValueError("Must provide either project_id or project_name")

        if project_name:
            project = self.get_project_by_name(project_name)
            if not project:
                raise ValueError(f"No project found with name: {project_name}")
            project_id = project.id

        project = self.get_project(project_id)
        label_config = project.label_config

        task_types = []

        # Check for object detection (RectangleLabels)
        if "<RectangleLabels" in label_config:
            task_types.append("object_detection")

        # Check for segmentation (PolygonLabels, BrushLabels)
        if "<PolygonLabels" in label_config or "<BrushLabels" in label_config:
            task_types.append("segmentation")

        # Check for classification (Choices, Labels)
        if "<Choices" in label_config or "<Labels" in label_config:
            task_types.append("classification")

        return task_types
    

if __name__ == "__main__":
    config = LabelStudioConfig(
        url="http://192.168.50.40:8080/",
        api_key="5c7de958cb0583e9b89f5795cdd9fc053aa105ba",
        gcp_creds="/home/joshua/Downloads/mt-2dportal-82aeba8b62e4.json"
    )
    label_studio = LabelStudio(config)
    print(label_studio.create_project(title="test"))