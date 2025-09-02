import os
import json
import time
import re
from typing import Optional, Union
from pathlib import Path
from label_studio_sdk import Client
from label_studio_sdk._legacy.project import Project as LSProject
from mindtrace.core import Mindtrace  # your base class
from mindtrace.jobs.utils.checks import ifnone



class LabelStudio(Client, Mindtrace):
    """Wrapper class around the Label Studio SDK client with Mindtrace integration.

    This class extends both the Label Studio `Client` and the `Mindtrace`
    base to provide convenient methods for working with label studio projects and
    integrating them into the Mindtrace ecosystem.
    """
    def __init__(self,url: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        """Initialize the LabelStudio client.

        Args:
            url (Optional[str]): Label Studio host URL. If not provided,
                defaults to ``self.config["MINDTRACE_DEFAULT_HOST_URLS"]["LabelStudio"]``.
            api_key (Optional[str]): Label Studio API key. If not provided,
                defaults to ``self.config["MINDTRACE_API_KEYS"]["LabelStudio"]``.
            **kwargs: Additional keyword arguments passed to ``Mindtrace``.

        Example::

        .. code-block:: python

            ls = LabelStudio(url="http://localhost:8080", api_key="my-api-key")
            print(ls.url)
            # http://localhost:8080
        """
        self.url = ifnone(url, default=self.config["MINDTRACE_DEFAULT_HOST_URLS"]["LabelStudio"])
        self.api_key = ifnone(api_key, default=self.config["MINDTRACE_API_KEYS"]["LabelStudio"])
        Client.__init__(self, url=self.url, api_key=self.api_key)
        Mindtrace.__init__(self, **kwargs)
        
        self.logger.info(f"Initialised LS at: {self.url}")

    def list_projects(self, page_size: int = 100, **query_params) -> list:
        """Return all projects across pages.

        Args:
            page_size (int): Number of projects per page. Defaults to ``100``.
            **query_params: Additional query parameters passed to the
                underlying API request.

        Returns:
            list: A list of project dictionaries returned from the API.

        Raises:
            Exception: If the API request fails.

        Example::

        .. code-block:: python

            ls = LabelStudio(api_key="my-api-key")
            projects = ls.list_projects()
            for p in projects:
                print(p["id"], p["title"])
        """
        self.logger.debug("Listing all projects (paginated)")
        projects = []
        page = 1
        while True:
            try:
                batch = Client.list_projects(self, page=page, page_size=page_size, **query_params)
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

    def get_project(self, project_name: Optional[str] = None, project_id: Optional[int] = None) -> LSProject:
        """Retrieve a specific project by name or ID.

        Args:
            project_name (Optional[str]): The name of the project to retrieve.
            project_id (Optional[int]): The ID of the project to retrieve.

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
            project = self._get_project_by_name(project_name)
            if project is None:
                raise ValueError(f"No project found with name: {project_name}")
            return project
        if project_id:
            self.logger.debug(f"Retrieving project with ID: {project_id}")
            try:
                return Client.get_project(self, project_id)
            except Exception as e:
                raise ValueError(f"No project found with id: {project_id}") from e
        raise ValueError("Must provide either project_name or project_id")


    def _get_project_by_name(self, project_name: str, page_size: int = 100, **query_params)-> LSProject:
        for p in self.list_projects(page_size=page_size, **query_params):
            if getattr(p, "title", None) == project_name:
                return p
        return None

    def create_project(self, project_name: str, description: str = None, label_config: str = None)-> LSProject:
        """Create a new project.

        Args:
            project_name: Project name
            description: Project description (optional)
            label_config: Label configuration in XML format (optional)

        Raises:
            ValueError: If a project with the same name already exists
        """
        # If a project with the same name exists, return it instead of creating a new one
        existing = self.get_project(project_name=project_name)
        if existing is not None:
            raise ValueError(
                f"Project with name '{project_name}' already exists (id={existing.id})"
            )

        kwargs = {"title": project_name}
        if description is not None:
            kwargs["description"] = description
        if label_config is not None:
            kwargs["label_config"] = label_config

        return Client.start_project(self, **kwargs)

    def delete_project(self, project_id: Optional[int] = None, project_name: Optional[str] = None) -> None:
        """Delete a project by ID or name.

        Args:
            project_id: Project ID to delete
            project_name: Project name to delete

        Raises:
            ValueError: If neither project_id nor project_name is provided,
                      or if project with given name is not found
        """
    
        if project_name:
            project = self._get_project_by_name(project_name)
            if not project:
                raise ValueError(f"No project found with name: {project_name}")
            project_id = project.id

        self.logger.info(f"Deleting project with ID: {project_id}")
        self.client.delete_project(project_id)
        self.logger.info("Project deleted successfully")

    def get_latest_project_part(self, pattern: str) -> tuple[Optional[int], Optional[str]]:
        """Find latest project part number matching pattern."""
        self.logger.debug(f"Searching for latest project matching pattern: {pattern}")
        projects = self.list_projects()
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

    def list_tasks(self, project_name: str = None, project_id: int = None) -> list:
        """Get all tasks in a project.

        Args:
            project_id: Project ID
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        tasks = project.get_tasks()
        return tasks

    def get_task(self, project_name: str = None, project_id: int = None, task_id: int = None) -> dict:
        """Get a specific task.

        Args:
            project_name: Project name
            project_id: Project ID
            task_id: Task ID
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        return project.get_task(task_id)

    def delete_task(self, project_name: str = None, project_id: int = None, task_id: int = None) -> None:
        """Delete a task.

        Args:
            project_name: Project name
            project_id: Project ID
            task_id: Task ID
        """
        project = self.get_project(project_name=project_name, project_id=project_id)
        project.delete_task(task_id)
        self.logger.info(f"Task {task_id} deleted from project {project_id}")

    def list_annotations(self, project_name: str = None, project_id: int = None, task_id: Optional[int] = None) -> list:
        """Get annotations for a task or all tasks."""
        project = self.get_project(project_name=project_name, project_id=project_id)
        try:
            if task_id:
                return project.get_annotations(task_id)
            else:
                # Use the tasks API to get annotations
                tasks = project.get_tasks()
                annotations = []
                for task in tasks:
                    task_annotations = project.get_annotations(task.id)
                    annotations.extend(task_annotations)
                return annotations
        except Exception as e:
            self.logger.error(f"Could not get annotations using get_annotations(): {e}")
            return []

    def list_import_storages(self, project_name: str = None, project_id: int = None) -> list:
        """Get all import storages for a project using the Label Studio SDK.

        Args:
            project_name: Project name
            project_id: Project ID
        """
        try:
            project = self.get_project(project_name=project_name, project_id=project_id)
            return project.get_import_storages()
        except Exception as e:
            self.logger.error(f"Failed to list import storages for project {project_name} or {project_id}: {e}")
            raise

    def list_export_storages(self, project_name: str = None, project_id: int = None) -> list:
        """Get all export storages for a project using the Label Studio SDK."""
        self.logger.debug(f"Listing export storages for project {project_id}")
        try:
            project = self.get_project(project_name=project_name, project_id=project_id)
            return project.get_export_storages()
        except Exception as e:
            self.logger.error(f"Failed to list export storages for project {project_name} or {project_id}: {e}")
            raise
    
    def create_annotation(
        self, 
        project_name: str = None, 
        project_id: int = None, 
        task_id: int = None, 
        annotation: dict = None) -> dict:
        """Create an annotation for a task."""
        self.logger.info(f"Creating annotation for task {task_id} in project {project_id}")
        try:
            result = self.get_project(project_name=project_name, project_id=project_id).create_annotation(task_id, annotation)
            self.logger.debug(f"Annotation created for task {task_id} in project {project_id}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to create annotation for task {task_id} in project {project_id}: {e}")
            raise
    
    def export_annotations(
        self,
        project_name: str = None,
        project_id: int = None,
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

    def sync_gcp_storage(
        self, 
        project_id: int, 
        storage_id: int, 
        storage_type: str = "import", 
        max_attempts: int = 100,
        retry_delay: int = 1
    ) -> bool:
        """Synchronise Google Cloud Storage.

        Args:
            project_id: Project ID
            storage_id: Storage ID to sync
            storage_type: Either "import" or "export"
            max_attempts: Maximum sync attempts
            retry_delay: Delay between sync attempts
        Returns:
            True if sync successful

        Raises:
            ValueError: If storage_type invalid
            TimeoutError: If sync times out
        """
        project = self.get_project(project_id)

        self.logger.info(f"Starting {storage_type} storage sync for storage ID: {storage_id}")

        if storage_type not in {"import", "export"}:
            raise ValueError(f"Invalid storage_type: {storage_type}. Use 'import' or 'export'.")

        attempt = 0
        retry_delay = 1
        last_error = None
        while attempt < max_attempts:
            try:
                if storage_type == "import":
                    response = project.sync_import_storage("gcs", storage_id)
                else:
                    response = project.sync_export_storage("gcs", storage_id)

                self.logger.debug(
                    f"Sync trigger response for storage {storage_id} (attempt {attempt + 1}/{max_attempts}): {response}"
                )
                return True
            except Exception as e:
                last_error = e
                attempt += 1
                self.logger.warning(
                    f"Sync attempt {attempt}/{max_attempts} failed for storage {storage_id}: {e}. "
                    f"Retrying in {retry_delay}s..."
                )
                time.sleep(min(retry_delay, 10))
                retry_delay = min(retry_delay * 2, 10)

        raise RuntimeError(
            f"Failed to trigger {storage_type} storage sync for storage ID {storage_id} after {max_attempts} attempts"
        ) from last_error

    def create_and_sync_gcp_storage(
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
                return self.sync_gcp_storage(project_id, storage["id"], storage_type)

        self.logger.info(f"Creating new {storage_type} storage for prefix {storage_prefix}")
        storage = self.create_gcp_cloud_storage(
            project_id=project_id,
            bucket=bucket_name,
            prefix=storage_prefix,
            storage_type=storage_type,
            google_application_credentials=gcp_credentials,
            regex_filter=regex_filter,
        )

    def create_gcp_cloud_storage(
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

        google_application_credentials = ifnone(google_application_credentials, default=self.config["MINDTRACE_GCP_CREDENTIALS_PATH"])

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