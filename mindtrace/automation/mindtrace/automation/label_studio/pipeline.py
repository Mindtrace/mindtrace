"""
Label Studio Pipeline Module.

This module provides a clean interface for Label Studio operations,
separating concerns and making the pipeline more maintainable.
"""

import os
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    """Configuration for Label Studio Pipeline."""
    
    # Label Studio API settings - all required
    label_studio_url: str
    label_studio_api_key: str
    gcp_credentials_path: str
    
    # GCS settings for Label Studio - all required
    gcs_bucket: str
    gcs_prefix: str
    
    # Project settings - all required
    project_title: str
    project_description: str
    interface_config: str
    
    # Optional settings
    upload_enabled: bool = True
    default_delay: int = 30
    
    def __post_init__(self):
        """Validate required configuration."""
        if not self.label_studio_url:
            raise ValueError("Label Studio URL is required")
        if not self.label_studio_api_key:
            raise ValueError("Label Studio API key is required")
        if not self.gcp_credentials_path:
            raise ValueError("GCP credentials path is required")
        if not os.path.exists(self.gcp_credentials_path):
            raise FileNotFoundError(f"GCP credentials file not found: {self.gcp_credentials_path}")
        if not self.gcs_bucket:
            raise ValueError("GCS bucket is required")
        if not self.gcs_prefix:
            raise ValueError("GCS prefix is required")
        if not self.project_title:
            raise ValueError("Project title is required")
        if not self.project_description:
            raise ValueError("Project description is required")
        if not self.interface_config:
            raise ValueError("Label Studio interface configuration is required")
        if not self.interface_config.strip().startswith('<View>') or not self.interface_config.strip().endswith('</View>'):
            raise ValueError("Invalid Label Studio interface configuration format - must be valid XML starting with <View> and ending with </View>")


class LabelStudioPipeline:
    """
    Handles Label Studio project creation and storage setup.
    
    This class encapsulates all Label Studio-specific operations,
    making it easier to maintain and modify Label Studio integration.
    """
    
    def __init__(self, config: PipelineConfig):
        """Initialize pipeline with configuration."""
        from .label_studio_api import LabelStudio, LabelStudioConfig
        
        self.config = config
        self.label_studio = LabelStudio(
            LabelStudioConfig(
                url=config.label_studio_url,
                api_key=config.label_studio_api_key,
                gcp_creds=config.gcp_credentials_path
            )
        )
    
    def create_project_from_job(
        self,
        job_info: Dict[str, Any],
        delay_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a Label Studio project from inference job information.
        
        Args:
            job_info: Job information dictionary from inference pipeline
            delay_seconds: Optional delay before storage sync (deprecated, handled by orchestrator)
        
        Returns:
            Dictionary containing project and storage information
        
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        if not job_info.get('job_id'):
            raise ValueError("Job ID is required in job_info")
        
        # Generate project title with job ID and timestamp
        job_id = job_info['job_id']
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        project_title = f"{self.config.project_title} - {job_id[:8]} - {timestamp}"
        
        # Create description using dates from config if available
        description = self.config.project_description
        if hasattr(self, '_config_dates') and self._config_dates:
            start_date = self._config_dates.get('start_date')
            end_date = self._config_dates.get('end_date')
            if start_date and end_date:
                description = f"Images from {start_date} to {end_date}"
        
        # Create project
        project = self.label_studio.create_project(
            title=project_title,
            description=description,
            label_config=self.config.interface_config.strip()
        )
        
        # Set up storage (delay is now handled by orchestrator)
        storage_info = self._setup_storage(
            project_id=project.id,
            job_info=job_info,
            delay_seconds=0  # No delay needed here
        )
        
        return {
            "project": project,
            "storage": storage_info,
            "project_url": f"{self.config.label_studio_url}/projects/{project.id}",
            "gcs_bucket": storage_info['bucket'],
            "gcs_prefix": storage_info['prefix']
        }
    
    def _setup_storage(
        self,
        project_id: int,
        job_info: Dict[str, Any],
        delay_seconds: int
    ) -> Dict[str, Any]:
        """
        Set up and sync GCS storage for a project.
        
        Args:
            project_id: Label Studio project ID
            job_info: Job information dictionary
            delay_seconds: Delay before syncing storage (deprecated, handled by orchestrator)
        
        Returns:
            Storage configuration information
        
        Raises:
            ValueError: If required GCS information is missing
        """
        # Extract GCS info from job info - must be present
        gcs_folder = job_info.get('gcs_folder')
        if not gcs_folder:
            raise ValueError("GCS folder information is required in job_info")
        
        # Parse GCS path
        if not gcs_folder.startswith('gs://'):
            raise ValueError(f"Invalid GCS path format: {gcs_folder}")
        
        parts = gcs_folder.replace('gs://', '').split('/')
        if len(parts) < 2:
            raise ValueError(f"Invalid GCS path structure: {gcs_folder}")
        
        gcs_bucket = parts[0]
        gcs_prefix = '/'.join(parts[1:]).rstrip('/')
        
        if not gcs_bucket or not gcs_prefix:
            raise ValueError(f"Invalid GCS path components: bucket={gcs_bucket}, prefix={gcs_prefix}")
        
        # Create and sync storage (delay is handled by orchestrator)
        storage = self.label_studio.create_cloud_storage(
            project_id=project_id,
            bucket=gcs_bucket,
            prefix=gcs_prefix,
            storage_type="import",
            google_application_credentials=self.config.gcp_credentials_path,
            regex_filter=r".*\.json$"
        )
        
        # Sync storage
        self.label_studio.sync_storage(
            project_id=project_id,
            storage_id=storage['id'],
            storage_type="import"
        )
        
        return {
            **storage,
            "bucket": gcs_bucket,
            "prefix": gcs_prefix
        }
    
    @classmethod
    def from_config_file(cls, config_path: Union[str, Path]) -> 'LabelStudioPipeline':
        """
        Create pipeline instance from a YAML config file.
        
        Args:
            config_path: Path to YAML config file
        
        Returns:
            LabelStudioPipeline instance
        
        Raises:
            ValueError: If required configuration is missing
            FileNotFoundError: If config file or GCP credentials not found
        """
        import yaml
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if 'label_studio' not in config:
            raise ValueError("'label_studio' section missing in config")
        
        label_studio_config = config['label_studio']
        if 'api' not in label_studio_config:
            raise ValueError("'label_studio.api' section missing in config")
        if 'project' not in label_studio_config:
            raise ValueError("'label_studio.project' section missing in config")
        if 'interface_config' not in label_studio_config:
            raise ValueError("'label_studio.interface_config' section missing in config")
        
        api_config = label_studio_config['api']
        project_config = label_studio_config['project']
        
        required_fields = ['url', 'api_key', 'gcp_credentials_path']
        missing_fields = [f for f in required_fields if not api_config.get(f)]
        if missing_fields:
            raise ValueError(f"Missing required Label Studio API fields: {', '.join(missing_fields)}")
        
        required_gcs = ['bucket', 'prefix']
        missing_gcs = [f for f in required_gcs if not label_studio_config.get(f)]
        if missing_gcs:
            raise ValueError(f"Missing required GCS fields: {', '.join(missing_gcs)}")
        
        required_project = ['title', 'description']
        missing_project = [f for f in required_project if not project_config.get(f)]
        if missing_project:
            raise ValueError(f"Missing required project fields: {', '.join(missing_project)}")
        
        # Extract dates from config for description
        config_dates = {}
        if 'start_date' in config:
            config_dates['start_date'] = config['start_date']
        if 'end_date' in config:
            config_dates['end_date'] = config['end_date']
        
        pipeline_instance = cls(
            PipelineConfig(
                label_studio_url=api_config['url'],
                label_studio_api_key=api_config['api_key'],
                gcp_credentials_path=api_config['gcp_credentials_path'],
                gcs_bucket=label_studio_config['bucket'],
                gcs_prefix=label_studio_config['prefix'],
                project_title=project_config['title'],
                project_description=project_config['description'],
                interface_config=label_studio_config['interface_config'],
                upload_enabled=label_studio_config.get('upload_enabled', True)
            )
        )
        
        # Store dates for use in description
        pipeline_instance._config_dates = config_dates
        
        return pipeline_instance 