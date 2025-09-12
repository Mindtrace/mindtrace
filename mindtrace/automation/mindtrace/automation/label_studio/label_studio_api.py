import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Union
from urllib.parse import parse_qs, urlparse

from label_studio_sdk import Client
from label_studio_sdk._legacy.project import Project as LSProject

from mindtrace.core import Mindtrace, ifnone

from .exceptions import (
    CredentialsNotFoundError,
    CredentialsReadError,
    ProjectAlreadyExistsError,
    ProjectFetchError,
    ProjectNotFoundError,
    StorageAlreadyExistsError,
    StorageCreationError,
    StorageNotFoundError,
)


class LabelStudio(Mindtrace):
    """Wrapper class around the Label Studio SDK client with Mindtrace integration.

    This class provides a higher-level interface for interacting with
    Label Studio projects while leveraging Mindtrace configuration and
    logging. It encapsulates the `label_studio_sdk.Client` so that
    Label Studio endpoints can be accessed with minimal setup and with
    config-driven defaults for URL, API keys, and credentials.

    Typical usage involves creating a `LabelStudio` instance and then
    calling project management or storage integration methods.
    """

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        """Initialize the LabelStudio client.

        Args:
            url: Label Studio host URL. If not provided,
                defaults to ``self.config["MINDTRACE_DEFAULT_HOST_URLS"]["LabelStudio"]``.
            api_key: Label Studio API key. If not provided,
                defaults to ``self.config["MINDTRACE_API_KEYS"]["LabelStudio"]``.
            **kwargs: Additional keyword arguments passed to ``Mindtrace``.

        Example::

        .. code-block:: python

            ls = LabelStudio(url="http://localhost:8080", api_key="my-api-key")
        """
        super().__init__(**kwargs)
        self.url = ifnone(url, default=self.config["MINDTRACE_DEFAULT_HOST_URLS"]["LabelStudio"])
        self.api_key = ifnone(api_key, default=self.config["MINDTRACE_API_KEYS"]["LabelStudio"])
        self.client = Client(url=self.url, api_key=self.api_key)
        self.logger.info(f"Initialised LS at: {self.url}")

    def create_project(
        self, project_name: str, description: Optional[str] = None, label_config: Optional[str] = None
    ) -> LSProject:
        """Create a new LSProject.

        Args:
            project_name: Project name
            description: Project description (optional)
            label_config: Label configuration in XML format (optional)

        Returns:
            LSProject: The created Label Studio project object.

        Raises:
            ProjectAlreadyExistsError: If a project with the same name already exists
        """
        try:
            existing = self.get_project(project_name=project_name)
        except ProjectNotFoundError:
            existing = None
        if existing is not None:
            raise ProjectAlreadyExistsError(f"Project with name '{project_name}' already exists (id={existing.id})")

        kwargs = {"title": project_name}
        if description is not None:
            kwargs["description"] = description
        if label_config is not None:
            kwargs["label_config"] = label_config

        return self.client.start_project(**kwargs)

    def get_projects(self, page_size: int = 100, **query_params) -> list[LSProject]:
        """List of LSProject in Label Studio (e.g., to search, validate names, or iterate through all projects)

        Args:
            page_size: Number of projects per page. Defaults to ``100``.
            **query_params: Additional query parameters passed to the
                underlying API request.

        Returns:
            list: A list of Label Studio LSProject

        Raises:
            Exception: If the API request fails.

        Example::

        .. code-block:: python

            ls = LabelStudio(api_key="my-api-key")
            projects = ls.get_projects()
            for p in projects:
                print(p["id"], p["title"])
        """
        self.logger.debug("Listing all projects (paginated)")
        projects = []
        page = 1
        while True:
            try:
                batch = self.client.list_projects(page=page, page_size=page_size, **query_params)
            except Exception as e:
                self.logger.error(f"Failed to list projects (page={page}): {e}")
                raise
            if not batch:
                break
            projects.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return projects

    def get_project(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> LSProject:
        """Retrieve a specific LSProject by name or ID.

        Args:
            project_name: The name of the project to retrieve.
            project_id: The ID of the project to retrieve.

        Returns:
            LSProject: The requested Label Studio project object.

        Raises:
            ValueError: If neither ``project_name`` nor ``project_id`` is provided,
                or if the project cannot be found.

        Example::

        .. code-block:: python

            ls = LabelStudio(api_key="my-api-key")
            project = ls.get_project(project_id=42)
            print(project.id, project.title)

            project = ls.get_project(project_name="Defect Detection")
            print(project.id, project.title)"""
        if project_name:
            self.logger.debug(f"Retrieving project with name: {project_name}")
            try:
                project = self._get_project_by_name(project_name)
            except Exception as e:
                raise ProjectFetchError(f"Failed to fetch project by name '{project_name}'") from e
            if project is None:
                raise ProjectNotFoundError(f"No project found with name: {project_name}")
            return project
        if project_id:
            self.logger.debug(f"Retrieving project with ID: {project_id}")
            try:
                return self.client.get_project(project_id)
            except Exception as e:
                raise ProjectFetchError(f"Failed to fetch project id '{project_id}'") from e
        raise ValueError("Must provide either project_name or project_id")

    def get_latest_project_part(self, pattern: str) -> tuple[Optional[int], Optional[str]]:
        """Find the latest project part number matching a given pattern.

        Args:
            pattern: Pattern to match project titles

        Returns:
            tuple[Optional[int], Optional[str]]: Latest project part number and title
        """
        self.logger.debug(f"Searching for latest project matching pattern: {pattern}")
        projects = self.get_projects()
        part_numbers = []
        for project in projects:
            match = re.search(pattern, project.title)
            if match:
                part_numbers.append((int(match.group(1)), project.title))
        if part_numbers:
            latest = max(part_numbers, key=lambda x: x[0])
            self.logger.debug(f"Latest matching project: part {latest[0]}, title '{latest[1]}'")
            return latest
        self.logger.debug("No projects matched the given pattern")
        return None, None

    def _get_project_by_name(self, project_name: str, page_size: int = 100, **query_params) -> LSProject:
        for p in self.get_projects(page_size=page_size, **query_params):
            if getattr(p, "title", None) == project_name:
                return p
        return None

    def delete_project(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> None:
        """Delete a project by ID or name.

        Args:
            project_name: Project name to delete
            project_id: Project ID to delete

        Raises:
            ValueError: If neither project_id nor project_name is provided,
                      or if project with given name is not found
        """
        if not project_name and not project_id:
            raise ValueError("Must provide either project_name or project_id")

        project = self.get_project(project_name=project_name, project_id=project_id)
        self.logger.info(f"Deleting project with ID: {project.id}")
        self.client.delete_project(project.id)
        self.logger.info("Project deleted successfully")

    def delete_projects_by_prefix(self, project_name_prefix: str) -> list[str]:
        """Delete all projects whose project_name start with the specified prefix.

        Args:
            project_name_prefix: The prefix to match against project project_names

        Returns:
            List of deleted project project_names

        Raises:
            ValueError: If project_name_prefix is empty
        """
        if not project_name_prefix:
            raise ValueError("project_name_prefix cannot be empty")

        self.logger.info(f"Finding projects with project_name prefix: {project_name_prefix}")
        projects = self.get_projects()
        matching_projects = [p for p in projects if p.title.startswith(project_name_prefix)]

        if not matching_projects:
            self.logger.info(f"No projects found with project_name prefix: {project_name_prefix}")
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

    def create_tasks_from_images(
        self,
        *,
        project_name: Optional[str] = None,
        project_id: Optional[int] = None,
        local_dir: Union[str, Path] = None,
        recursive: bool = True,
        batch_size: int = 10,
    ) -> int:
        """Replicate Label Studio UI "Import" by uploading files directly so tasks use /data/upload paths.

        This sends file binaries to Label Studio (POST /api/projects/{id}/import with multipart file),
        which stores them under its media upload directory and creates tasks like:
        {"data": {"image": "/data/upload/..."}, ...}.

        Args:
            project_name: Project name in Label Studio.
            project_id: Project ID in Label Studio.
            local_dir: Absolute local directory containing files to upload.
            recursive: Recurse into subdirectories.
            batch_size: Number of files to process per log batch (uploads are per-file).

        Returns:
            int: Number of tasks created (sum of returned task IDs).
        """
        if local_dir is None:
            raise ValueError("local_dir must be provided")
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")

        project = self.get_project(project_name=project_name, project_id=project_id)

        root_dir = Path(local_dir).resolve()
        if not root_dir.exists() or not root_dir.is_dir():
            raise ValueError(f"local_dir does not exist or is not a directory: {root_dir}")

        # Accept common image types; extend as needed
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
        candidates = root_dir.rglob("*") if recursive else root_dir.iterdir()

        def is_image_file(p: Path) -> bool:
            return p.is_file() and p.suffix.lower() in image_extensions

        batch: list[Path] = []
        total_created = 0
        batch_index = 0

        def process_batch(paths: list[Path]) -> int:
            created = 0
            if not paths:
                return 0
            self.logger.info(f"Uploading batch {batch_index + 1} (size={len(paths)}) to project {project.id}")
            for path in paths:
                try:
                    created_ids = project.import_tasks(str(path))
                    created += len(created_ids) if created_ids is not None else 0
                except Exception as e:
                    self.logger.warning(f"Failed to import file '{path}': {e}")
            return created

        for entry in candidates:
            if not is_image_file(entry):
                continue
            batch.append(entry)
            if len(batch) >= batch_size:
                total_created += process_batch(batch)
                batch_index += 1
                batch = []

        # process remaining
        if batch:
            total_created += process_batch(batch)

        if total_created == 0:
            self.logger.info(f"No images found under: {root_dir}. Supported image extensions are: {image_extensions}")

        self.logger.info(f"Uploaded {total_created} tasks to project '{project.title}' (ID: {project.id})")
        return total_created

    def get_tasks(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> list:
        """List all tasks in a project.

        Args:
            project_name: Project name
            project_id: Project ID

        Returns:
            list: A list of Label Studio Task objects
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        tasks = project.get_tasks()
        return tasks

    def get_task(
        self, *, project_name: Optional[str] = None, project_id: Optional[int] = None, task_id: Optional[int] = None
    ) -> dict:
        """Get a specific task.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio
            task_id: Task ID of Label Studio

        Returns:
            dict: A dictionary containing the task data
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        return project.get_task(task_id)

    def get_task_types(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> list[str]:
        """Determine the task types in a project by analyzing its label configuration.
        XML tags vs task types:
        <RectangleLabels> -> object_detection
        <PolygonLabels> or <BrushLabels> -> segmentation
        <Choices> or <Labels> -> classification

        Args:
            project_name: Project name to analyze
            project_id: Project ID to analyze

        Returns:
            List of task types found in the project (e.g., ['object_detection', 'classification', 'segmentation'])

        Raises:
            ValueError: If neither project_id nor project_name is provided,
                    or if project with given name is not found
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        label_config = project.label_config

        task_types = []

        if "<RectangleLabels" in label_config:
            task_types.append("object_detection")

        if "<PolygonLabels" in label_config or "<BrushLabels" in label_config:
            task_types.append("segmentation")

        if "<Choices" in label_config or "<Labels" in label_config:
            task_types.append("classification")

        return task_types

    def delete_task(
        self, *, project_name: Optional[str] = None, project_id: Optional[int] = None, task_id: Optional[int] = None
    ) -> None:
        """Delete a task.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio
            task_id: Task ID of Label Studio

        Returns:
            None
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        project.delete_task(task_id)
        self.logger.info(f"Task {task_id} deleted from project {project_id}")

    def create_annotation(
        self, *, project_name: str = None, project_id: int = None, task_id: int = None, annotation: dict = None
    ) -> dict:
        """Create an annotation for a task.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio
            task_id: Task ID of Label Studio
            annotation: Annotation to create

        Returns:
            dict: A dictionary containing the created annotation
        """
        self.logger.info(f"Creating annotation for task {task_id} in project {project_id}")
        try:
            result = self.get_project(project_name=project_name, project_id=project_id).create_annotation(
                task_id, annotation
            )
            self.logger.debug(f"Annotation created for task {task_id} in project {project_id}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to create annotation for task {task_id} in project {project_id}: {e}")
            raise

    def get_annotations(
        self, *, project_name: Optional[str] = None, project_id: Optional[int] = None, task_id: Optional[int] = None
    ) -> list:
        """Get annotations for a task_id or all tasks.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio
            task_id: Task ID of Label Studio

        Returns:
            list: A list of Label Studio Annotation objects
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        if task_id:
            return project.get_task(task_id).get("annotations", [])
        # Use the tasks API to get annotations
        tasks = project.get_tasks()
        annotations = []
        for task in tasks:
            task_annotations = task.get("annotations", [])
            annotations.extend(task_annotations)
        return annotations

    def export_annotations(
        self,
        *,
        project_name: str = None,
        project_id: int = None,
        export_type: str = "YOLO",
        download_all_tasks: bool = True,
        download_resources: bool = True,
        ids: list = None,
        export_location: str = None,
    ) -> Union[list, Path]:
        """Export project annotations in various formats.

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
        project = self.get_project(project_name=project_name, project_id=project_id)
        self.logger.info(f"Exporting project {project_name} or {project_id} in {export_type} format")
        try:
            result = project.export_tasks(
                export_type=export_type,
                download_all_tasks=download_all_tasks,
                download_resources=download_resources,
                ids=ids,
                export_location=export_location,
            )
            if export_location:
                self.logger.info(f"Exported to {export_location}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to export annotations for project {project_name} or {project_id}: {e}")
            raise

    def create_gcp_storage(
        self,
        *,
        project_name: Optional[str] = None,
        project_id: Optional[int] = None,
        bucket: str = None,
        prefix: Optional[str] = None,
        storage_type: str = "import",
        google_application_credentials: Optional[str] = None,
        regex_filter: Optional[str] = None,
        use_blob_urls: bool = False,
        presign: Optional[bool] = None,
        presign_ttl: Optional[int] = None,
    ) -> dict:
        """Create a Google Cloud Storage for import or export.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio
            bucket: GCS bucket name
            prefix: Optional path prefix in bucket
            storage_type: Either "import" or "export"
            google_application_credentials: Path to credentials JSON file
            regex_filter: Regex filter for matching object keys when importing
            use_blob_urls: If True, don't copy objects; reference them via blob URLs
            presign: If True and supported, generate presigned URLs (import storage)
            presign_ttl: TTL (in minutes) for presigned URLs when presign=True

        Returns:
            dict: A dictionary containing the created storage details

        Raises:
            StorageCreationError: If storage creation fails
            CredentialsNotFoundError: If credentials file is missing or invalid
            StorageAlreadyExistsError: If a storage with the same title already exists
            requests.exceptions.RequestException: If API request fails
            json.JSONDecodeError: If credentials file contains invalid JSON
            OSError: If there are file system errors
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        storage_name = (
            f"GCS {storage_type.title()} {bucket}/{prefix}" if prefix else f"GCS {storage_type.title()} {bucket}"
        )
        # Prevent duplicate storages with same title
        if storage_type == "import":
            existing_storages = project.get_import_storages()
        else:
            existing_storages = project.get_export_storages()

        for s in existing_storages:
            s_title = s.get("title")
            if s_title == storage_name:
                raise StorageAlreadyExistsError(
                    f"A {storage_type} storage for title '{storage_name}' already exists (id={s.get('id')})"
                )

        google_application_credentials = ifnone(
            google_application_credentials, default=self.config["MINDTRACE_GCP_CREDENTIALS_PATH"]
        )

        if not google_application_credentials or not os.path.exists(google_application_credentials):
            raise CredentialsNotFoundError(f"GCP credentials file not found ({google_application_credentials})")

        try:
            with open(google_application_credentials, "r") as f:
                credentials_content = f.read()
                json.loads(credentials_content)
        except (json.JSONDecodeError, OSError) as e:
            raise CredentialsReadError(f"Error reading credentials file: {str(e)}")

        self.logger.info(f"Creating {storage_type} storage: {storage_name}")
        self.logger.debug(f"Using bucket: {bucket}, prefix: {prefix}")

        try:
            if storage_type == "import":
                use_blob_urls = bool(use_blob_urls)
                effective_presign = True if presign is None else bool(presign)
                effective_presign_ttl = 1 if presign_ttl is None else int(presign_ttl)

                return project.connect_google_import_storage(
                    bucket=bucket,
                    prefix=prefix,
                    regex_filter=regex_filter,
                    use_blob_urls=use_blob_urls,
                    presign=effective_presign,
                    presign_ttl=effective_presign_ttl,
                    title=storage_name,
                    description="Imported via Label Studio SDK",
                    google_application_credentials=credentials_content,
                )
            else:
                return project.connect_google_export_storage(
                    bucket=bucket,
                    prefix=prefix,
                    use_blob_urls=use_blob_urls,
                    title=storage_name,
                    description="Exported via Label Studio SDK",
                    google_application_credentials=credentials_content,
                )
        except Exception as e:
            self.logger.error(f"Failed to create storage: {str(e)}")
            raise StorageCreationError(f"Failed to create {storage_type} storage '{storage_name}'") from e

    def sync_gcp_storage(
        self,
        *,
        project_name: Optional[str] = None,
        project_id: Optional[int] = None,
        storage_id: Optional[int] = None,
        storage_prefix: Optional[str] = None,
        storage_type: str = "import",
        max_attempts: int = 3,
        retry_delay: int = 1,
    ) -> bool:
        """Synchronise Google Cloud Storage. The function will trigger the sync of the storage and return True if the sync is successful
        The function will import or export the tasks to the storage from the project respectively as specified by the storage_type.
        If storage_id is provided, the function will sync the storage with the given id.
        If storage_prefix is provided, the function will sync the storage with the given prefix.
        If both storage_id and storage_prefix are provided, the function will sync the storage with the given id.
        If neither storage_id nor storage_prefix are provided, the function will raise an error.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio
            storage_id: Storage ID to sync
            storage_prefix: Storage prefix to sync. Optional, specify the prefix or folder within the GCS bucket with your data
            storage_type: Either "import" or "export"
            max_attempts: Maximum sync attempts
            retry_delay: Delay between sync attempts
        Returns:
            True if sync successful

        Raises:
            ValueError: If storage_type invalid
            StorageNotFoundError: Storage not found
            TimeoutError: If sync times out
        """
        project = self.get_project(project_name=project_name, project_id=project_id)

        self.logger.info(f"Starting {storage_type} storage sync for storage ID: {storage_id}")

        if storage_type not in {"import", "export"}:
            raise ValueError(f"Invalid storage_type: {storage_type}. Use 'import' or 'export'.")

        attempt = 0
        last_error = None
        while attempt < max_attempts:
            try:
                if storage_id:
                    if storage_type == "import":
                        response = project.sync_import_storage("gcs", storage_id)
                    else:
                        response = project.sync_export_storage("gcs", storage_id)

                    self.logger.debug(
                        f"Sync trigger response for storage {storage_id} (attempt {attempt + 1}/{max_attempts}): {response}"
                    )
                    return True
                elif storage_prefix:
                    if storage_type == "import":
                        storages = project.get_import_storages()
                        if not storages:
                            raise StorageNotFoundError(f"No import storages found for project {project_name}")
                        for storage in storages:
                            if storage["prefix"] == storage_prefix:
                                self.logger.info(f"Found existing storage with prefix {storage_prefix}")
                                response = project.sync_import_storage("gcs", storage["id"])
                                return True
                    else:
                        storages = project.get_export_storages()
                        if not storages:
                            raise StorageNotFoundError(f"No export storages found for project {project_name}")
                        for storage in storages:
                            if storage["prefix"] == storage_prefix:
                                self.logger.info(f"Found existing storage with prefix {storage_prefix}")
                                response = project.sync_export_storage("gcs", storage["id"])
                                return True
                else:
                    raise ValueError("Either storage_id or storage_prefix must be provided")
            except (StorageNotFoundError, ValueError) as e:
                raise e
            except Exception as e:
                last_error = e
                attempt += 1
                self.logger.warning(
                    f"Sync attempt {attempt}/{max_attempts} failed for storage {storage_id}: {e}. "
                    f"Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)

        raise RuntimeError(
            f"Failed to trigger {storage_type} storage sync for storage ID {storage_id} after {max_attempts} attempts"
        ) from last_error

    def list_import_storages(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> list:
        """List all import storages for a project.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio

        Returns:
            list: A list of Label Studio Storage objects
        """
        try:
            project = self.get_project(project_name=project_name, project_id=project_id)
            return project.get_import_storages()
        except Exception as e:
            self.logger.error(f"Failed to list import storages for project {project_name} or {project_id}: {e}")
            raise

    def list_export_storages(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> list:
        """List all export storages for a project.

        Args:
            project_name: Project name of Label Studio
            project_id: Project ID of Label Studio

        Returns:
            list: A list of Label Studio Storage objects
        """
        self.logger.debug(f"Listing export storages for project {project_id}")
        try:
            project = self.get_project(project_name=project_name, project_id=project_id)
            return project.get_export_storages()
        except Exception as e:
            self.logger.error(f"Failed to list export storages for project {project_name} or {project_id}: {e}")
            raise

    def export_projects_by_prefix(
        self,
        project_name_prefix: str,
        output_dir: str = "./export_output",
        export_type: str = "YOLO",
        download_resources: bool = True,
    ) -> list[str]:
        """Export all projects whose project_names start with the specified prefix.

        Args:
            project_name_prefix: The prefix to match against project project_names
            output_dir: Base directory for exports
            export_type: Format to export in ('YOLO', 'JSON', 'CSV', etc.)
            download_resources: Whether to download images/resources

        Returns:
            List of exported project project_names

        Raises:
            ValueError: If project_name_prefix is empty
        """
        if not project_name_prefix:
            raise ValueError("project_name_prefix cannot be empty")

        self.logger.info(f"Finding projects with project_name prefix: {project_name_prefix}")
        projects = self.get_projects()
        matching_projects = [p for p in projects if p.title.startswith(project_name_prefix)]

        if not matching_projects:
            self.logger.info(f"No projects found with project_name prefix: {project_name_prefix}")
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

    def _extract_gcs_path_from_label_studio_url(self, label_studio_url: str) -> Optional[str]:
        """Extract GCS path from a Label Studio presign URL.

        Args:
            label_studio_url: Label Studio presign URL

        Returns:
            GCS path in gs://bucket/path format, or None if not a valid Label Studio URL
        """
        if not label_studio_url:
            return None

        try:
            parsed = urlparse(label_studio_url)

            if "presign" not in parsed.path:
                return None

            query_params = parse_qs(parsed.query)
            fileuri = query_params.get("fileuri", [None])[0]

            if not fileuri:
                return None

            try:
                decoded_bytes = base64.b64decode(fileuri)
                gcs_path = decoded_bytes.decode("utf-8")

                if gcs_path.startswith("gs://"):
                    return gcs_path
                else:
                    self.logger.warning(f"Decoded path is not a GCS path: {gcs_path}")
                    return None

            except Exception as e:
                self.logger.warning(f"Error decoding base64 fileuri '{fileuri}': {str(e)}")
                return None

        except Exception as e:
            self.logger.warning(f"Error extracting GCS path from Label Studio URL '{label_studio_url}': {str(e)}")
            return None

    def _extract_image_path_from_task(self, task: dict) -> Optional[str]:
        """Extract image path from a task dictionary.

        Args:
            task: Label Studio task dictionary

        Returns:
            GCS path if extractable, original URL otherwise, None if not found
        """
        if not task or not isinstance(task, dict):
            return None

        if "data" in task and isinstance(task["data"], dict):
            data = task["data"]
            if "image" in data:
                image_url = data["image"]
                gcs_path = self._extract_gcs_path_from_label_studio_url(image_url)
                if gcs_path:
                    return gcs_path
                else:
                    return image_url

    def get_project_image_paths(self, *, project_name: Optional[str] = None, project_id: Optional[int] = None) -> set:
        """Get all image paths from a specific project.

        Args:
            project_name: Project name to analyze
            project_id: Label Studio project ID

        Returns:
            Set of image paths/URLs used in the project
        """
        try:
            tasks = self.get_tasks(project_name=project_name, project_id=project_id)
            image_paths = set()

            for task in tasks:
                image_path = self._extract_image_path_from_task(task)
                if image_path:
                    image_paths.add(image_path)

            self.logger.info(f"Found {len(image_paths)} unique images in project {project_id}")
            return image_paths

        except Exception as e:
            self.logger.error(f"Error getting image paths from project {project_id}: {str(e)}")
            return set()
