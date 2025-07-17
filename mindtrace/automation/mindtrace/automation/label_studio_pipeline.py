import os
import argparse
import yaml
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from mindtrace.automation.infer_folder import run_inference
from mindtrace.automation.convert_to_label_studio import (
    create_individual_label_studio_files_with_gcs,
    upload_label_studio_jsons_to_gcs
)
from mindtrace.automation.label_studio.pipeline import LabelStudioPipeline


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
        
        # Validate required sections
        required_sections = ['gcp', 'label_studio', 'start_date', 'end_date', 'output_folder']
        missing = [section for section in required_sections if section not in config]
        if missing:
            raise ValueError(f"Missing required config sections: {missing}")
        
        return config
    
    def run_inference(self, custom_job_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the complete inference pipeline and return structured results."""
        # Use the refactored inference function
        job_info = run_inference(self.config_path, custom_job_id)
        
        if not job_info:
            raise RuntimeError("Inference failed - no images processed")
        
        # Set job ID for orchestrator
        self.job_id = job_info['job_id']
        
        # Add timestamp and ensure gcs_folder is set correctly
        job_info['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        if 'gcs_folder' not in job_info:
            job_info['gcs_folder'] = f"gs://{self.config['label_studio']['bucket']}/{self.config['label_studio']['prefix']}/{self.job_id}/"
        
        # Save job info
        job_info_path = os.path.join(self.config['output_folder'], f"label_studio_job_{self.job_id}.json")
        with open(job_info_path, 'w') as f:
            json.dump(job_info, f, indent=2, default=str)
        
        return job_info
    
    def run_conversion(self, job_info: Dict[str, Any]) -> Dict[str, Any]:
        """Run Label Studio conversion and return structured results."""
        # Create output directory for JSON files
        json_output_dir = os.path.join(job_info['config']['output_folder'], f"label_studio_jsons_{self.job_id}")
        os.makedirs(json_output_dir, exist_ok=True)
        
        # Convert to Label Studio format
        created_files = create_individual_label_studio_files_with_gcs(
            output_folder=job_info['config']['output_folder'],
            gcs_mapping=job_info['gcs_path_mapping'],
            output_dir=json_output_dir,
            class_mapping=None,  # Could be made configurable
            mask_task_names=job_info['config'].get('mask_tasks', ['zone_segmentation'])
        )
        
        # Upload to GCS if enabled
        uploaded_urls = []
        if job_info['config']['label_studio'].get('upload_enabled', False):
            uploaded_urls = upload_label_studio_jsons_to_gcs(
                local_json_files=created_files,
                gcs_config=job_info['config']['label_studio'],
                job_id=self.job_id,
                credentials_path=job_info['config']['gcp']['credentials_file']
            )
        
        # Update job info with conversion results
        job_info.update({
            "conversion_results": {
                "created_files": created_files,
                "uploaded_urls": uploaded_urls,
                "json_output_dir": json_output_dir,
                "total_files": len(created_files)
            }
        })
        
        # Save updated job info
        job_info_path = os.path.join(job_info['config']['output_folder'], f"label_studio_job_{self.job_id}.json")
        with open(job_info_path, 'w') as f:
            json.dump(job_info, f, indent=2, default=str)
        
        return job_info
    
    def create_label_studio_project(self, job_info: Dict[str, Any], delay_seconds: int = 30) -> Dict[str, Any]:
        """Create Label Studio project and return structured results."""
        # Initialize Label Studio pipeline
        pipeline = LabelStudioPipeline.from_config_file(self.config_path)
        
        # Create project
        project_info = pipeline.create_project_from_job(
            job_info=job_info,
            delay_seconds=delay_seconds
        )
        
        # Update job info with project results
        job_info.update({
            "label_studio_project": {
                "project_id": project_info['project'].id,
                "project_url": project_info['project_url'],
                "storage_info": project_info['storage'],
                "gcs_bucket": project_info['gcs_bucket'],
                "gcs_prefix": project_info['gcs_prefix']
            }
        })
        
        # Save final job info
        job_info_path = os.path.join(job_info['config']['output_folder'], f"label_studio_job_{self.job_id}.json")
        with open(job_info_path, 'w') as f:
            json.dump(job_info, f, indent=2, default=str)
        
        return job_info
    
    def run_complete_pipeline(self, custom_job_id: Optional[str] = None, delay_seconds: int = 30) -> Dict[str, Any]:
        """Run the complete pipeline and return structured results."""
        # Step 1: Run inference
        job_info = self.run_inference(custom_job_id)
        
        # Step 2: Run conversion (includes upload)
        job_info = self.run_conversion(job_info)
        
        # Step 2.5: Wait for uploads to complete if any files were uploaded
        if job_info.get('conversion_results', {}).get('uploaded_urls'):
            if delay_seconds > 0:
                print(f"Waiting {delay_seconds} seconds for GCS uploads to complete...")
                time.sleep(delay_seconds)
        
        # Step 3: Create Label Studio project
        job_info = self.create_label_studio_project(job_info, delay_seconds=0)  # No delay needed here
        
        return job_info


def main():
    parser = argparse.ArgumentParser(description="Complete Label Studio Pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--job_id", type=str, default=None, help="Custom job ID")
    parser.add_argument("--delay", type=int, default=30, help="Delay in seconds before syncing storage (default: 30)")
    parser.add_argument("--skip_inference", action="store_true", help="Skip inference and use existing job data")
    
    args = parser.parse_args()
    
    try:
        orchestrator = PipelineOrchestrator(args.config)
        
        if args.skip_inference:
            # Load existing job info
            if not args.job_id:
                raise ValueError("--job_id is required when using --skip_inference")
            
            job_info_path = os.path.join(orchestrator.config['output_folder'], f"label_studio_job_{args.job_id}.json")
            if not os.path.exists(job_info_path):
                raise FileNotFoundError(f"Job info file not found: {job_info_path}")
            
            with open(job_info_path, 'r') as f:
                job_info = json.load(f)
            
            # Run conversion and project creation
            job_info = orchestrator.run_conversion(job_info)
            
            # Wait for uploads to complete if any files were uploaded
            if job_info.get('conversion_results', {}).get('uploaded_urls'):
                if args.delay > 0:
                    print(f"Waiting {args.delay} seconds for GCS uploads to complete...")
                    time.sleep(args.delay)
            
            job_info = orchestrator.create_label_studio_project(job_info, delay_seconds=0)
        else:
            # Run complete pipeline
            job_info = orchestrator.run_complete_pipeline(args.job_id, args.delay)
        
        # Print summary
        print("=== PIPELINE COMPLETED SUCCESSFULLY ===")
        print(f"Job ID: {job_info['job_id']}")
        if 'label_studio_project' in job_info:
            print(f"Project ID: {job_info['label_studio_project']['project_id']}")
            print(f"Project URL: {job_info['label_studio_project']['project_url']}")
            print(f"GCS Folder: {job_info['gcs_folder']}")
        print(f"Job info saved to: {os.path.join(job_info['config']['output_folder'], f'label_studio_job_{job_info['job_id']}.json')}")
        
        return 0
        
    except Exception as e:
        print(f"Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main()) 