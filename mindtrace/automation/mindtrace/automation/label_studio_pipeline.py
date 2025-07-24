import os
import argparse
import yaml
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from mindtrace.automation.infer_folder import run_inference
from mindtrace.automation.label_studio.utils import (
    create_individual_label_studio_files_with_gcs,
    upload_label_studio_jsons_to_gcs
)
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig


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
        
        required_sections = ['gcp', 'label_studio', 'start_date', 'end_date', 'output_folder']
        missing = [section for section in required_sections if section not in config]
        if missing:
            raise ValueError(f"Missing required config sections: {missing}")
        
        return config
    
    def run_inference(self, custom_job_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the complete inference pipeline and return structured results."""
        job_info = run_inference(self.config_path, custom_job_id)
        
        if not job_info:
            raise RuntimeError("Inference failed - no images processed")
        
        self.job_id = job_info['job_id']
        
        job_info['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        if 'gcs_folder' not in job_info:
            job_info['gcs_folder'] = f"gs://{self.config['label_studio']['bucket']}/{self.config['label_studio']['prefix']}/{self.job_id}/"
        
        return job_info
    
    def run_conversion(self, job_info: Dict[str, Any]) -> Dict[str, Any]:
        """Run Label Studio conversion and return structured results."""
        label_studio_config = job_info['config']['label_studio']
        generate_all_masks = label_studio_config.get('generate_mask', False)
        mask_source = 'sam'
        
        mask_from_name = label_studio_config.get('mask_from_name')
        mask_tool_type = label_studio_config.get('mask_tool_type')
        polygon_epsilon_factor = label_studio_config.get('polygon_epsilon_factor', 0.005)

        print(f"Mask source: {mask_source}", '--------------------------------')
        print(f"Label Studio generate all masks: {generate_all_masks}", '--------------------------------')
        print(f"Mask from name: {mask_from_name}", '--------------------------------')
        print(f"Mask tool type: {mask_tool_type}", '--------------------------------')

        if not mask_from_name or not mask_tool_type:
            raise ValueError("Config file must specify 'mask_from_name' and 'mask_tool_type' under 'label_studio' section.")
        
        json_output_dir = os.path.join(job_info['config']['output_folder'], f"label_studio_jsons_{self.job_id}")
        os.makedirs(json_output_dir, exist_ok=True)
        
        created_files = create_individual_label_studio_files_with_gcs(
            output_folder=job_info['config']['output_folder'],
            gcs_mapping=job_info['gcs_path_mapping'],
            output_dir=json_output_dir,
            mask_from_name=mask_from_name,
            mask_tool_type=mask_tool_type,
            class_mapping=None,
            mask_task_names=job_info['config'].get('mask_tasks', ['zone_segmentation']),
            box_task_names=job_info['config'].get('bounding_box_tasks', ['zone_segmentation']),
            polygon_epsilon_factor=polygon_epsilon_factor
        )
        
        uploaded_urls = []
        if job_info['config']['label_studio'].get('upload_enabled', False):
            uploaded_urls = upload_label_studio_jsons_to_gcs(
                local_json_files=created_files,
                gcs_config=job_info['config']['label_studio'],
                job_id=self.job_id,
                credentials_path=job_info['config']['gcp']['credentials_file']
            )
        
        job_info.update({
            "conversion_results": {
                "created_files": created_files,
                "uploaded_urls": uploaded_urls,
                "json_output_dir": json_output_dir,
                "total_files": len(created_files)
            }
        })
        
        return job_info
    
    def create_label_studio_project(self, job_info: Dict[str, Any], delay_seconds: int = 30) -> Dict[str, Any]:
        """Create Label Studio project and return structured results."""
        label_studio_config = self.config['label_studio']
        api_config = label_studio_config['api']
        project_config = label_studio_config['project']
        
        label_studio = LabelStudio(
            LabelStudioConfig(
                url=api_config['url'],
                api_key=api_config['api_key'],
                gcp_creds=api_config['gcp_credentials_path']
            )
        )
        
        job_id = job_info['job_id']
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        project_title = f"{project_config['title']} - {job_id[:8]} - {timestamp}"
        
        description = project_config['description']
        if 'start_date' in self.config and 'end_date' in self.config:
            start_date = self.config['start_date']
            end_date = self.config['end_date']
            description = f"Images from {start_date} to {end_date}"
        
        gcs_folder = job_info.get('gcs_folder')
        if not gcs_folder or not gcs_folder.startswith('gs://'):
            raise ValueError(f"Invalid GCS folder format: {gcs_folder}")
        
        parts = gcs_folder.replace('gs://', '').split('/')
        gcs_bucket = parts[0]
        gcs_prefix = '/'.join(parts[1:]).rstrip('/')
        
        project, storage = label_studio.create_project_with_storage(
            title=project_title,
            bucket=gcs_bucket,
            prefix=gcs_prefix,
            label_config=label_studio_config['interface_config'].strip(),
            description=description,
            google_application_credentials=api_config['gcp_credentials_path'],
            regex_filter=r".*\.json$"
        )
        
        job_info.update({
            "label_studio_project": {
                "project_id": project.id,
                "project_url": f"{api_config['url']}/projects/{project.id}",
                "storage_info": storage,
                "gcs_bucket": gcs_bucket,
                "gcs_prefix": gcs_prefix
            }
        })
        
        return job_info

    def run_complete_pipeline(self, custom_job_id: Optional[str] = None, delay_seconds: int = 30) -> Dict[str, Any]:
        """Run the complete pipeline and return structured results."""
        job_info = self.run_inference(custom_job_id)
        job_info = self.run_conversion(job_info)
        
        if job_info.get('conversion_results', {}).get('uploaded_urls'):
            if delay_seconds > 0:
                print(f"Waiting {delay_seconds} seconds for GCS uploads to complete...")
                time.sleep(delay_seconds)
        
        job_info = self.create_label_studio_project(job_info, delay_seconds=0)
        
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
        print(f"GCS Folder: {job_info.get('gcs_folder', 'N/A')}")
        print(f"Total Files: {job_info.get('conversion_results', {}).get('total_files', 0)}")
        
        return 0
        
    except Exception as e:
        print(f"Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main()) 