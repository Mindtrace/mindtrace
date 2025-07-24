from label_studio_sdk import Client
import os
from typing import Optional, Union, Any, Dict, List
from pathlib import Path
import re
import json
import random
import shutil
import cv2
import numpy as np
from PIL import Image
from dataclasses import dataclass
from mindtrace.core import Mindtrace
from urllib.parse import urlparse, parse_qs
import base64
from mindtrace.storage.gcs import GCSStorageHandler
from tqdm import tqdm
from .utils import create_dataset_structure, create_manifest, split_dataset, organize_files_into_splits
from mtrix.datalake import Datalake


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

    def create_project(self, title: str, description: str = None, label_config: str = None) -> dict:
        """Create a new project.

        Args:
            title: Project name
            description: Project description (optional)
            label_config: Label configuration in XML format (optional)
        """
        kwargs = {"title": title}
        if description is not None:
            kwargs["description"] = description
        if label_config is not None:
            kwargs["label_config"] = label_config
        
        return self.client.create_project(**kwargs)

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
        """Get all tasks in a project.
        
        Args:
            project_id: Project ID
        """
        try:
            project = self.get_project(project_id)
            tasks = project.get_tasks()
            return tasks
            
        except Exception as e:
            self.logger.error(f"Error getting tasks for project {project_id}: {e}")
            return []

    def get_task(self, project_id: int, task_id: int) -> dict:
        """Get a specific task."""
        return self.get_project(project_id).get_task(task_id)

    def delete_task(self, project_id: int, task_id: int) -> None:
        """Delete a task."""
        self.get_project(project_id).delete_task(task_id)

    def list_annotations(self, project_id: int, task_id: Optional[int] = None) -> list:
        """Get annotations for a task or all tasks."""
        project = self.get_project(project_id)
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
            self.logger.warning(f"Could not get annotations using get_annotations(): {e}")
            # Fallback: try to get annotations from tasks
            try:
                tasks = project.get_tasks()
                annotations = []
                for task in tasks:
                    if hasattr(task, 'annotations') and task.annotations:
                        annotations.extend(task.annotations)
                return annotations
            except Exception as e2:
                self.logger.error(f"Could not get annotations from tasks either: {e2}")
                return []

    def list_import_storages(self, project_id: int) -> list:
        """Get all import storages for a project using the Label Studio SDK."""
        project = self.get_project(project_id)
        return project.get_import_storages()

    def list_export_storages(self, project_id: int) -> list:
        """Get all export storages for a project using the Label Studio SDK."""
        project = self.get_project(project_id)
        return project.get_export_storages()

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

        if "<RectangleLabels" in label_config:
            task_types.append("object_detection")

        if "<PolygonLabels" in label_config or "<BrushLabels" in label_config:
            task_types.append("segmentation")

        if "<Choices" in label_config or "<Labels" in label_config:
            task_types.append("classification")

        return task_types
    
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
            
            if 'presign' not in parsed.path:
                return None
            
            query_params = parse_qs(parsed.query)
            fileuri = query_params.get('fileuri', [None])[0]
            
            if not fileuri:
                return None
            
            try:
                decoded_bytes = base64.b64decode(fileuri)
                gcs_path = decoded_bytes.decode('utf-8')
                
                if gcs_path.startswith('gs://'):
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
            
        if 'data' in task and isinstance(task['data'], dict):
            data = task['data']
            if 'image' in data:
                image_url = data['image']
                
                gcs_path = self._extract_gcs_path_from_label_studio_url(image_url)
                if gcs_path:
                    return gcs_path
                else:
                    return image_url
        
        if 'image' in task:
            image_url = task['image']
            
            gcs_path = self._extract_gcs_path_from_label_studio_url(image_url)
            if gcs_path:
                return gcs_path
            else:
                return image_url
            
        return None
    
    def get_project_image_paths(self, project_id: int) -> set:
        """Get all image paths from a specific project.
        
        Args:
            project_id: Label Studio project ID
            
        Returns:
            Set of image paths/URLs used in the project
        """
        try:
            tasks = self.list_tasks(project_id)
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
    
    def get_all_existing_image_paths(self, project_title_prefix: Optional[str] = None) -> set:
        """Get all image paths from existing Label Studio projects.
        
        Args:
            project_title_prefix: Optional prefix to filter projects by title.
                                 If None, checks all projects.
            
        Returns:
            Set of all image paths/URLs from matching projects
        """
        try:
            projects = self.list_projects()
            all_image_paths = set()
            
            if project_title_prefix:
                projects = [p for p in projects if p.title.startswith(project_title_prefix)]
                self.logger.info(f"Checking {len(projects)} projects with prefix '{project_title_prefix}'")
            else:
                self.logger.info(f"Checking all {len(projects)} projects")
            
            for project in projects:
                try:
                    project_paths = self.get_project_image_paths(project.id)
                    all_image_paths.update(project_paths)
                    self.logger.debug(f"Project '{project.title}' (ID: {project.id}): {len(project_paths)} images")
                except Exception as e:
                    self.logger.warning(f"Failed to get images from project '{project.title}' (ID: {project.id}): {str(e)}")
                    continue
            
            self.logger.info(f"Total unique images found across all projects: {len(all_image_paths)}")
            return all_image_paths
            
        except Exception as e:
            self.logger.error(f"Error getting all existing image paths: {str(e)}")
            return set()
    
    def _get_image_filename_from_path(self, image_path: str) -> Optional[str]:
        """Extract filename from image path/URL.
        
        Args:
            image_path: Image path or URL (GCS, HTTP, or local path)
            
        Returns:
            Filename if extractable, None otherwise
        """
        if not image_path:
            return None
            
        try:
            if image_path.startswith('gs://'):
                return image_path.split('/')[-1]
            
            elif image_path.startswith(('http://', 'https://')):
                parsed = urlparse(image_path)
                filename = parsed.path.split('/')[-1]
                return filename.split('?')[0] if filename else None
            
            else:
                return os.path.basename(image_path)
                
        except Exception as e:
            self.logger.warning(f"Error extracting filename from path '{image_path}': {str(e)}")
            return None
    
    def get_all_existing_gcs_paths(self, project_title_prefix: Optional[str] = None) -> set:
        """Get all GCS paths from existing Label Studio projects.
        
        Args:
            project_title_prefix: Optional prefix to filter projects by title.
                                 If None, checks all projects.
            
        Returns:
            Set of all GCS paths (gs://bucket/path format) from matching projects
        """
        image_paths = self.get_all_existing_image_paths(project_title_prefix)
        gcs_paths = set()
        
        for image_path in image_paths:
            if image_path.startswith('gs://'):
                gcs_paths.add(image_path)
            elif 'presign' in image_path and 'fileuri=' in image_path:
                gcs_path = self._extract_gcs_path_from_label_studio_url(image_path)
                if gcs_path:
                    gcs_paths.add(gcs_path)
        
        self.logger.info(f"Total unique GCS paths found: {len(gcs_paths)}")
        return gcs_paths

    def _transform_annotation_to_datalake(self, data: list, output_dir: Path, class_mapping: dict, all_masks: bool = False) -> dict:
        images = {}
        for task in data:
            filename = task['data']['image'].split('/')[-1]
            image_entry = {"file_name": filename, "bboxes": []}

            mask_labels = []
            for ann in task.get('annotations', []):
                for result in ann.get('result', []):
                    if result['type'] == 'rectanglelabels':
                        bbox = {
                            "x": int(result['value']['x']),
                            "y": int(result['value']['y']),
                            "width": int(result['value']['width']),
                            "height": int(result['value']['height']),
                            "label": result['value']['rectanglelabels'][0]
                        }
                        image_entry['bboxes'].append(bbox)
                    elif result['type'] == 'polygonlabels':
                        label = result['value']['polygonlabels'][0]
                        mask_labels.append(label)

            mask_file = (output_dir / "masks" / f"{Path(filename).stem}_mask.png")
            
            # Include mask if it exists and has labels, OR if all_masks is enabled and mask file exists
            if mask_file.exists() and (mask_labels or all_masks):
                image_entry['masks'] = {
                    "file_name": str(mask_file.name),
                    "labels": sorted(mask_labels) if mask_labels else []
                }

            images[filename] = image_entry
        return {"images": images}

    def export_project_to_json(
        self,
        project_id: int,
        output_dir: str,
        download_path: str,
        download_images: bool = False,
        generate_masks: bool = False,
        all_masks: bool = False,
        splits: Optional[Dict[str, List[str]]] = None,
        version: str = "1.0.0"
    ) -> Dict[str, any]:
        """Export project annotations to JSON format.
        
        Args:
            project_id: Label Studio project ID
            output_dir: Output directory for export
            download_path: Path where images should be downloaded
            download_images: Whether to download images from GCS
            generate_masks: Whether to generate segmentation masks from polygon annotations
            all_masks: Whether to generate mask files for all images (including empty ones)
            splits: Optional dictionary of split names to lists of image filenames
            version: Dataset version (default: "1.0.0")
        
        Returns:
            Dict with export statistics
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export JSON
        json_export_path = output_dir / "export.json"
        self.export_annotations(
            project_id=project_id,
            export_type="JSON",
            download_all_tasks=True,
            download_resources=False,
            export_location=str(json_export_path)
        )
        
        with open(json_export_path, 'r') as f:
            data = json.load(f)
        
        gcs_paths = []
        local_image_paths = {}
        
        if download_images or generate_masks:  
            import_storages = self.list_import_storages(project_id)
            if not import_storages:
                self.logger.warning("No import storages found, cannot download images")
                download_images = False
                generate_masks = False
            else:
                storage_info = import_storages[0]
                bucket_name = storage_info.get('bucket')
                if not bucket_name:
                    self.logger.warning("No bucket name found in storage info, cannot download images")
                    download_images = False
                    generate_masks = False
                else:
                    gcs_handler = GCSStorageHandler(bucket_name=bucket_name)
                    temp_images_dir = Path(download_path)
                    temp_images_dir.mkdir(exist_ok=True)
                    self.logger.info(f"Downloading images from bucket '{bucket_name}' to {temp_images_dir}")
        
        for task in data:
            if 'data' in task and 'image' in task['data']:
                image_path = task['data']['image']
                if image_path.startswith('gs://'):
                    gcs_paths.append(image_path)
        
        if download_images or generate_masks:
            if gcs_paths:
                self.logger.info(f"Starting batch download of {len(gcs_paths)} images...")
                file_map = {}
                for gcs_path in gcs_paths:
                    filename = gcs_path.split('/')[-1]
                    local_path = temp_images_dir / filename
                    file_map[gcs_path] = str(local_path)
                
                downloaded_paths, errors = gcs_handler.download_files(file_map, max_workers=8)
                local_image_paths.update(downloaded_paths)
                self.logger.info(f"✅ Successfully downloaded: {len(downloaded_paths)} images")
                if errors:
                    self.logger.warning(f"Failed to download: {len(errors)} images")
                    for path, error in errors.items():
                        self.logger.debug(f"  Failed {path}: {error}")
        
        if generate_masks:
            # Create masks directory
            masks_dir = output_dir / "masks"
            masks_dir.mkdir(exist_ok=True)
            
            # Get unique labels and create class mapping
            unique_labels = set()
            for task in data:
                for ann in task.get('annotations', []):
                    for result in ann.get('result', []):
                        if result['type'] == 'polygonlabels':
                            unique_labels.update(result['value']['polygonlabels'])
            
            class2idx = {label: idx + 1 for idx, label in enumerate(sorted(unique_labels))} 
            
            # Save class mapping
            class_mapping = {
                'idx2label': {str(idx): label for label, idx in class2idx.items()},
                'label2idx': class2idx
            }
            with open(output_dir / 'class_mapping.json', 'w') as f:
                json.dump(class_mapping, f, indent=2)
            
            self.logger.info(f"Generating masks for {len(data)} tasks...")
            for task in tqdm(data, desc="Generating masks"):
                has_polygons = False
                polygon_results = []
                for ann in task.get('annotations', []):
                    for result in ann.get('result', []):
                        if result['type'] == 'polygonlabels':
                            has_polygons = True
                            polygon_results.append(result)
                
                image_path = task['data']['image']
                local_path = local_image_paths.get(image_path)
                if not local_path:
                    continue
                
                try:
                    image = Image.open(local_path)
                    w, h = image.size
               
                    mask = np.zeros((h, w), dtype=np.uint8) 
                    
                    # Only process polygons if they exist
                    if has_polygons:
                        polygon_results.sort(key=lambda x: class2idx[x['value']['polygonlabels'][0]])
                        
                        for result in polygon_results:
                            label = result['value']['polygonlabels'][0]
                            class_id = class2idx[label]
                            
                            points = (np.array(result['value']['points']) * np.array([w, h]) / 100).astype(np.int32)
                            points = points.reshape((-1, 1, 2))
                            
                            cv2.fillPoly(mask, [points], color=class_id)
                    
                    # Generate mask file if we have polygons
                    if has_polygons:
                        mask_filename = f"{Path(local_path).stem}_mask.png"
                        mask_path = masks_dir / mask_filename
                        cv2.imwrite(str(mask_path), mask)
                        self.logger.debug(f"Generated mask with polygons: {mask_filename}")
                    # Generate empty mask file if all_masks is enabled and we don't have polygons
                    elif all_masks:
                        mask_filename = f"{Path(local_path).stem}_mask.png"
                        mask_path = masks_dir / mask_filename
                        cv2.imwrite(str(mask_path), mask)
                        self.logger.debug(f"Generated empty mask: {mask_filename}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to generate mask for {image_path}: {e}")
                
            self.logger.info("✅ Mask generation completed")

            data = self._transform_annotation_to_datalake(data, output_dir, class_mapping, all_masks)
        
        with open(output_dir / "annotations.json", 'w') as f:
            json.dump(data, f, indent=2)
        
        json_export_path.unlink()
        
        # Count generated masks
        generated_mask_count = 0
        if generate_masks:
            masks_dir = output_dir / "masks"
            if masks_dir.exists():
                generated_mask_count = len(list(masks_dir.glob("*.png")))
        
        stats = {
            'total_tasks': len(data),
            'downloaded_images': len(local_image_paths) if download_images or generate_masks else 0,
            'generated_masks': generated_mask_count,
            'class_mapping': class2idx if generate_masks else None,
            'images': data['images']  # Include the transformed data
        }
        
        self.logger.info(f"Export completed successfully!")
        self.logger.info(f"Total tasks: {stats['total_tasks']}")
        if download_images:
            self.logger.info(f"Images downloaded to: {temp_images_dir}")
        if generate_masks:
            self.logger.info(f"Masks generated in: {masks_dir}")
            self.logger.info(f"Generated {stats['generated_masks']} mask files")
            if all_masks:
                self.logger.info(f"Generated masks for all images (including empty ones)")
            self.logger.info(f"Classes: {list(class2idx.keys())}")
        
        return stats

    def convert_and_publish_to_datalake(
        self,
        project_id: int,
        output_dir: Path,
        download_path: str,
        dataset_name: str,
        version: str = "1.0.0",
        train_split: float = 0.8,
        test_split: float = 0.2,
        download_images: bool = True,
        generate_masks: bool = True,
        all_masks: bool = False,
        description: str = "",
        seed: int = 42,
        hf_token: str = None,
        gcp_creds_path: str = None,
        new_dataset: bool = True,
        detection_classes: Optional[List[str]] = None,
        segmentation_classes: Optional[List[str]] = None,
        sam_config: Optional[Dict] = None  # Add SAM config parameter
    ) -> Dict[str, Any]:
        """Convert Label Studio project to datalake format with train/test splits."""
        # Validate splits
        if abs(train_split + test_split - 1.0) > 1e-6:
            raise ValueError("Train and test splits must sum to 1.0")
            
        dataset_dir = output_dir / dataset_name
        temp_dir = Path(download_path)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        create_dataset_structure(dataset_dir, splits=['train', 'test'])
        
        export_result = self.export_project_to_json(
            project_id=project_id,
            output_dir=temp_dir,
            download_path=download_path,
            download_images=download_images,
            generate_masks=generate_masks,
            all_masks=all_masks
        )
        
        if not export_result['images']:
            raise ValueError(f"No data found for project {project_id}")
        
        split_result = split_dataset(
            data=list(export_result['images'].keys()),
            train_split=train_split,
            val_split=0.0,
            test_split=test_split,
            seed=seed
        )
        
        moved_files = organize_files_into_splits(
            base_dir=dataset_dir,
            split_assignments=split_result['splits'],
            source_images_dir=temp_dir,
            source_masks_dir=temp_dir / "masks" if generate_masks else None
        )

        sam = None
        sam_generate_all_masks = False
        if sam_config:
            from mtrix.models import SegmentAnything as SAM
            sam = SAM(
                model=sam_config.get('model_version', 'vit_l'),
                device=sam_config.get('device', 'cuda')
            )
            sam_generate_all_masks = sam_config.get('generate_masks', False)
        
        for split_name, filenames in split_result['splits'].items():
            if not filenames:  # Skip empty splits
                continue

            split_dir = dataset_dir / 'splits' / split_name
            split_annotations = {
                "images": {
                    img: export_result['images'][img]
                    for img in filenames
                }
            }

            # Process SAM masks if enabled
            if sam:
                print(f"Processing SAM masks for {split_name} split...")
                
                # Create sam_masks directory for this split
                sam_masks_dir = split_dir / 'sam_masks'
                sam_masks_dir.mkdir(exist_ok=True)


                for img_name, img_data in tqdm(split_annotations['images'].items(), desc=f"Processing SAM masks for {split_name}"):
                    image_path = split_dir / 'images' / img_name
                    if not image_path.exists():
                        continue

                    image = Image.open(image_path)
                    img_width, img_height = image.size

                    # Check if we have bounding boxes
                    has_bboxes = bool(img_data.get('bboxes'))
                    
                    # Skip if no bboxes and we're not generating all masks
                    if not has_bboxes and not sam_generate_all_masks:
                        continue

                    # Convert bboxes to format SAM expects [x1, y1, x2, y2] (convert from percentage to pixels)
                    bboxes = []
                    if has_bboxes:
                        for bbox in img_data['bboxes']:
                            # Convert percentage to pixels
                            x1 = int(bbox['x'] * img_width / 100)
                            y1 = int(bbox['y'] * img_height / 100)
                            x2 = int((bbox['x'] + bbox['width']) * img_width / 100)
                            y2 = int((bbox['y'] + bbox['height']) * img_height / 100)
                            bboxes.append([x1, y1, x2, y2])
                    sam.set_image(image)

                    # Combine all masks into one image
                    combined_mask = np.zeros((img_height, img_width), dtype=np.uint8)
                    bbox_references = []

                    # Process bounding boxes if they exist
                    if has_bboxes and bboxes:
                        for idx, (bbox_coords, bbox) in enumerate(zip(bboxes, img_data['bboxes'])):
                            
                            mask = sam.compute_mask(bbox=np.array(bbox_coords), image=None)
                            
                            if mask.shape != (img_height, img_width):
                                print(f"Warning: Mask shape {mask.shape} doesn't match image shape ({img_height}, {img_width})")
                                continue
                            
                            combined_mask[mask] = 255
                            bbox_references.append({
                                'bbox_id': str(idx + 1),
                                'label': bbox['label']
                            })

                    mask_filename = f"{Path(img_name).stem}_sam_masks.png"
                    cv2.imwrite(
                        str(sam_masks_dir / mask_filename),
                        combined_mask
                    )

                    img_data['sam_masks'] = {
                        'file_name': mask_filename,
                        'bbox_references': bbox_references
                    }

            annotations_file = split_dir / f"annotations_v{version}.json"
            with open(annotations_file, 'w') as f:
                json.dump(split_annotations, f, indent=2)
        
        create_manifest(
            base_dir=dataset_dir,
            name=dataset_name,
            version=version,
            splits=moved_files,
            class_mapping=export_result['class_mapping'],
            description=description,
            detection_classes=detection_classes,
            segmentation_classes=segmentation_classes
        )

        # Create and publish dataset using Datalake
        if hf_token and gcp_creds_path:            
            self.logger.info(f"{'Creating new' if new_dataset else 'Updating existing'} dataset: {dataset_name}")
            datalake = Datalake(
                    hf_token=hf_token,
                    gcp_creds_path=gcp_creds_path
                )
            if new_dataset:
                datalake.create_dataset(
                    source=str(dataset_dir),
                    dataset_name=dataset_name,
                    version=version
                )
            else:
                datalake.update_dataset(
                    src=str(dataset_dir),
                    dataset_name=dataset_name,
                    version=version
                )
            
            datalake.publish_dataset(
                dataset_name=dataset_name,
                version=version
            )
        
        return {
            'dataset_dir': str(dataset_dir.absolute()),
            'manifest': str(dataset_dir / f"manifest_v{version}.json"),
            'splits': {
                'train': len(split_result['splits']['train']),
                'test': len(split_result['splits']['test'])
            },
            'class_mapping': export_result['class_mapping']
        }