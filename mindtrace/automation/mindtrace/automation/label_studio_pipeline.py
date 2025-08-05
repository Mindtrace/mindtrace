import os
import argparse
import yaml
import json
import time
import uuid
import glob
from pathlib import Path
from typing import Dict, Any, Optional

from mindtrace.automation.infer_folder import run_inference
from mindtrace.automation.label_studio.utils import (
    create_individual_label_studio_files_with_gcs,
    upload_label_studio_jsons_to_gcs
)
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig
from mindtrace.storage.gcs import GCSStorageHandler


class PipelineOrchestrator:
    """Orchestrates the complete Label Studio pipeline with proper data exchange."""

    def __init__(self, config_path: str):
        """Initialize orchestrator with config file."""
        self.config_path = config_path
        self.config = self._load_config()
        self.job_id = None

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate configuration."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        data_source = config.get('data_source', 'gcp')
        if data_source == 'gcp':
            required_sections = ['gcp', 'label_studio', 'start_date', 'end_date', 'output_folder']
        elif data_source == 'local':
            required_sections = ['local_image_path', 'label_studio', 'output_folder', 'gcp']
        else:
            raise ValueError(f"Invalid data_source: {data_source}. Must be 'gcp' or 'local'.")

        missing = [section for section in required_sections if section not in config]
        if missing:
            raise ValueError(f"Missing required config sections for data_source '{data_source}': {missing}")

        return config

    def _run_gcp_inference(self, custom_job_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the inference pipeline using GCP data source."""
        job_info = run_inference(self.config_path, custom_job_id)

        if not job_info:
            raise RuntimeError("Inference failed - no images processed")

        self.job_id = job_info['job_id']

        job_info['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        job_info['gcs_folder'] = f"gs://{self.config['label_studio']['bucket']}/{self.config['label_studio']['prefix']}/{self.job_id}/"

        return job_info

    def _run_local_inference(self, custom_job_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the inference pipeline using local file system."""
        self.job_id = custom_job_id or str(uuid.uuid4())

        job_info = run_inference(self.config_path, self.job_id)

        if not job_info:
            raise RuntimeError("Inference failed for local images.")

        job_info['job_id'] = self.job_id
        job_info['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        job_info['config'] = self.config
        job_info['gcs_folder'] = f"gs://{self.config['label_studio']['bucket']}/{self.config['label_studio']['prefix']}/{self.job_id}/"

        return job_info

    def run_inference(self, custom_job_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the complete inference pipeline and return structured results."""
        data_source = self.config.get('data_source', 'gcp')
        if data_source == 'gcp':
            return self._run_gcp_inference(custom_job_id)
        elif data_source == 'local':
            return self._run_local_inference(custom_job_id)
        else:
            raise ValueError(f"Invalid data_source: {data_source}")

    def _upload_local_data_to_gcs(self, job_info: Dict[str, Any]) -> Dict[str, Any]:
        """Uploads local images to GCS and updates the mapping."""
        print("=== UPLOADING LOCAL IMAGES TO GCS ===")
        gcs_handler = GCSStorageHandler(
            bucket_name=self.config['label_studio']['bucket'],
            credentials_path=self.config['gcp']['credentials_file']
        )

        image_gcs_prefix = f"{self.config['label_studio']['prefix']}/{self.job_id}/images"

        updated_gcs_mapping = {}

        image_paths = [p.replace('file://', '') for p in job_info['gcs_path_mapping'].keys()]

        for local_path in image_paths:
            filename = os.path.basename(local_path)
            remote_path = f"{image_gcs_prefix}/{filename}"
            gcs_url = gcs_handler.upload(local_path, remote_path)
            updated_gcs_mapping[filename] = gcs_url
            print(f"Uploaded {filename} to {gcs_url}")

        job_info['gcs_path_mapping'] = updated_gcs_mapping
        print("=== LOCAL IMAGE UPLOAD COMPLETE ===\n")
        return job_info


    def run_conversion(self, job_info: Dict[str, Any]) -> Dict[str, Any]:
        """Run Label Studio conversion and return structured results."""
        label_studio_config = job_info['config']['label_studio']

        created_files = create_individual_label_studio_files_with_gcs(
            output_folder=job_info['config']['output_folder'],
            gcs_mapping=job_info['gcs_path_mapping'],
            output_dir=os.path.join(job_info['config']['output_folder'], f"label_studio_jsons_{self.job_id}"),
            mask_from_name=label_studio_config.get('mask_from_name'),
            mask_tool_type=label_studio_config.get('mask_tool_type'),
            class_mapping=job_info.get('class_mappings'),
            mask_task_names=job_info['config'].get('mask_tasks', []),
            box_task_names=job_info['config'].get('bounding_box_tasks', []),
            polygon_epsilon_factor=label_studio_config.get('polygon_epsilon_factor', 0.005)
        )

        print("=== UPLOADING TASK JSONS TO GCS ===")
        uploaded_urls = upload_label_studio_jsons_to_gcs(
            local_json_files=created_files,
            gcs_config=job_info['config']['label_studio'],
            job_id=self.job_id,
            credentials_path=job_info['config']['gcp']['credentials_file']
        )
        print("=== TASK JSON UPLOAD COMPLETE ===\n")

        job_info.update({
            "conversion_results": {
                "created_files": created_files,
                "uploaded_urls": uploaded_urls,
                "total_files": len(created_files)
            }
        })

        return job_info

    def create_label_studio_project(self, job_info: Dict[str, Any], delay_seconds: int = 30) -> Dict[str, Any]:
        """Create a Label Studio project and configure its data source."""
        label_studio_config = self.config['label_studio']
        api_config = label_studio_config['api']
        project_config = label_studio_config['project']

        label_studio = LabelStudio(
            LabelStudioConfig(
                url=api_config['url'],
                api_key=api_config['api_key'],
                gcp_creds=api_config.get('gcp_credentials_path')
            )
        )

        job_id = job_info['job_id']
        timestamp = time.strftime("%y%m%d-%H%M") # Shorter timestamp
        base_title = project_config.get('title', 'Inference Run')
        project_title = f"{base_title[:25]} - {job_id[:6]} - {timestamp}"


        description = project_config.get('description', '')
        if self.config.get('data_source') == 'gcp' and 'start_date' in self.config and 'end_date' in self.config:
            description = f"Images from {self.config['start_date']} to {self.config['end_date']}"

        project = label_studio.create_project(
            title=project_title,
            label_config=label_studio_config['interface_config'].strip(),
            description=description
        )
        print(f"Successfully created Label Studio project '{project.title}' (ID: {project.id})")

        gcs_folder = job_info.get('gcs_folder')
        if not gcs_folder or not gcs_folder.startswith('gs://'):
            raise ValueError(f"Invalid GCS folder format: {gcs_folder}")

        parts = gcs_folder.replace('gs://', '').split('/')
        gcs_bucket = parts[0]
        gcs_prefix = '/'.join(parts[1:]).rstrip('/')

        print(f"Connecting project to GCS bucket '{gcs_bucket}' with prefix '{gcs_prefix}'")
        storage = label_studio.create_cloud_storage(
            project_id=project.id,
            bucket=gcs_bucket,
            prefix=gcs_prefix,
            storage_type="import",
            google_application_credentials=api_config.get('gcp_credentials_path'),
            regex_filter=r".*\.json$"
        )
        label_studio.sync_storage(project.id, storage['id'])

        job_info['label_studio_project'] = {
            "project_id": project.id,
            "project_url": f"{api_config['url']}/projects/{project.id}",
            "storage_info": storage,
            "gcs_bucket": gcs_bucket,
            "gcs_prefix": gcs_prefix
        }

        return job_info

    def run_complete_pipeline(self, custom_job_id: Optional[str] = None, delay_seconds: int = 30) -> Dict[str, Any]:
        """Run the complete pipeline and return structured results."""
        print("\n=== STARTING INFERENCE STAGE ===")
        job_info = self.run_inference(custom_job_id)
        print("=== INFERENCE STAGE COMPLETE ===\n")

        # if self.config.get('data_source') == 'local':
        #     job_info = self._upload_local_data_to_gcs(job_info)

        # print("=== STARTING LABEL STUDIO CONVERSION STAGE ===")
        # job_info = self.run_conversion(job_info)
        # print("=== LABEL STUDIO CONVERSION COMPLETE ===\n")

        # if job_info.get('conversion_results', {}).get('uploaded_urls'):
        #     if delay_seconds > 0:
        #         print(f"Waiting {delay_seconds} seconds for GCS uploads to complete...")
        #         time.sleep(delay_seconds)

        # print("=== STARTING LABEL STUDIO PROJECT CREATION STAGE ===")
        # job_info = self.create_label_studio_project(job_info, delay_seconds=0)
        # print("=== LABEL STUDIO PROJECT CREATION COMPLETE ===\n")

        return job_info


def main():
    parser = argparse.ArgumentParser(description="Complete Label Studio Pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--job_id", type=str, default=None, help="Custom job ID")
    parser.add_argument("--delay", type=int, default=30, help="Delay in seconds before syncing storage (default: 30)")

    args = parser.parse_args()

    try:
        orchestrator = PipelineOrchestrator(args.config)
        job_info = orchestrator.run_complete_pipeline(args.job_id, args.delay)

        print("=== PIPELINE COMPLETED SUCCESSFULLY ===")
        print(f"Job ID: {job_info['job_id']}")
        print(f"Project URL: {job_info.get('label_studio_project', {}).get('project_url', 'N/A')}")
        if 'gcs_folder' in job_info:
            print(f"GCS Folder: {job_info.get('gcs_folder', 'N/A')}")
        print(f"Total Files: {job_info.get('conversion_results', {}).get('total_files', 0)}")

        return 0

    except Exception as e:
        print(f"Pipeline failed: {e}")
        return 1


if __name__ == "__main__":

    exit(main())
