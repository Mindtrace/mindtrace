#!/usr/bin/env python3
"""
Complete Label Studio Pipeline:
1. Run inference on images
2. Convert results to Label Studio format
3. Upload JSON files to GCS
4. Create Label Studio project
5. Set up and sync GCS storage
"""

import os
import argparse
import yaml
import json
import time
import uuid
import subprocess
import sys
from pathlib import Path
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig


def run_inference_with_conversion(config_path: str, job_id: str = None) -> dict:
    """
    Run the complete inference and conversion pipeline.
    
    Args:
        config_path: Path to YAML config file
        job_id: Optional custom job ID
    
    Returns:
        Dictionary with job information
    """
    print("=== STEP 1: Running Inference Pipeline ===")
    
    # Run inference
    inference_cmd = [
        sys.executable, "-m", "infer_folder",
        "--config", config_path
    ]
    
    if job_id:
        inference_cmd.extend(["--job_id", job_id])
    
    print(f"Running inference command: {' '.join(inference_cmd)}")
    result = subprocess.run(inference_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Inference failed with return code {result.returncode}")
        if result.stderr:
            print("Error output:", result.stderr)
        raise RuntimeError("Inference pipeline failed")
    
    print("Inference completed successfully")
    if result.stdout:
        print("Inference output:", result.stdout)
    
    # Extract job ID from output if not provided
    if not job_id:
        for line in result.stdout.split('\n'):
            if 'Starting inference job with ID:' in line:
                job_id = line.split('ID:')[-1].strip()
                break
    
    # Load config to get job info
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Look for job info file
    job_info_path = os.path.join(config['output_folder'], f"label_studio_job_{job_id}.json")
    job_info = {}
    
    if os.path.exists(job_info_path):
        with open(job_info_path, 'r') as f:
            job_info = json.load(f)
        print(f"Loaded job info from: {job_info_path}")
    else:
        print(f"Warning: Job info file not found at {job_info_path}")
        # Create basic job info
        job_info = {
            "job_id": job_id,
            "config": config,
            "status": "inference_completed"
        }
    
    return job_info


def create_label_studio_project_with_storage(
    job_info: dict,
    label_studio_config: dict,
    project_title: str = None,
    label_config: str = None,
    delay_seconds: int = 30
) -> dict:
    """
    Create Label Studio project and set up GCS storage.
    
    Args:
        job_info: Job information from inference pipeline
        label_studio_config: Label Studio configuration
        project_title: Optional custom project title
        label_config: Optional custom label configuration
        delay_seconds: Delay before syncing storage to allow uploads to complete
    
    Returns:
        Dictionary with project and storage information
    """
    print("=== STEP 2: Creating Label Studio Project ===")
    
    # Initialize Label Studio client
    config = LabelStudioConfig(
        url=label_studio_config['url'],
        api_key=label_studio_config['api_key'],
        gcp_creds=label_studio_config.get('gcp_credentials_path')
    )
    
    label_studio = LabelStudio(config)
    
    # Generate project title if not provided
    if not project_title:
        job_id = job_info['job_id']
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        project_title = f"Inference_Job_{job_id[:8]}_{timestamp}"
    
    # Default label configuration if not provided
    if not label_config:
        label_config = '''
        <View>
            <Image name="image" value="$image"/>
            <RectangleLabels name="bbox" toName="image">
                <Label value="zone" background="#ff0000"/>
                <Label value="spatter" background="#00ff00"/>
            </RectangleLabels>
            <BrushLabels name="brush" toName="image">
                <Label value="zone_mask" background="#0000ff"/>
                <Label value="spatter_mask" background="#ffff00"/>
            </BrushLabels>
        </View>
        '''
    
    print(f"Creating project: {project_title}")
    
    # Create project
    project = label_studio.create_project(
        title=project_title,
        description=f"Auto-generated project for inference job {job_info['job_id']}",
        label_config=label_config
    )
    
    print(f"Created project with ID: {project.id}")
    
    # Set up GCS import storage
    print("=== STEP 3: Setting up GCS Import Storage ===")
    
    gcs_bucket = job_info.get('gcs_folder', '').replace('gs://', '').split('/')[0]
    gcs_prefix = '/'.join(job_info.get('gcs_folder', '').replace('gs://', '').split('/')[1:]).rstrip('/')
    
    if not gcs_bucket or not gcs_prefix:
        # Fallback to config values
        config_data = job_info.get('config', {})
        gcs_bucket = config_data.get('label_studio', {}).get('bucket', '')
        gcs_prefix = f"{config_data.get('label_studio', {}).get('prefix', 'labelstudio-jsons')}/{job_info['job_id']}"
    
    print(f"Setting up GCS storage: gs://{gcs_bucket}/{gcs_prefix}")
    
    # Wait for uploads to complete
    if delay_seconds > 0:
        print(f"Waiting {delay_seconds} seconds for GCS uploads to complete...")
        time.sleep(delay_seconds)
    
    # Create and sync storage
    try:
        storage = label_studio.create_cloud_storage(
            project_id=project.id,
            bucket=gcs_bucket,
            prefix=gcs_prefix,
            storage_type="import",
            google_application_credentials=label_studio_config.get('gcp_credentials_path'),
            regex_filter=r".*\.json$"  # Only import JSON files
        )
        
        print(f"Created import storage with ID: {storage['id']}")
        
        # Sync storage
        print("Syncing GCS storage...")
        label_studio.sync_storage(
            project_id=project.id,
            storage_id=storage['id'],
            storage_type="import"
        )
        
        print("Storage sync completed successfully")
        
        return {
            "project": project,
            "storage": storage,
            "project_url": f"{label_studio_config['url']}/projects/{project.id}",
            "gcs_bucket": gcs_bucket,
            "gcs_prefix": gcs_prefix
        }
        
    except Exception as e:
        print(f"Error setting up storage: {e}")
        print("Project created but storage setup failed. You can manually configure storage in Label Studio.")
        return {
            "project": project,
            "storage": None,
            "project_url": f"{label_studio_config['url']}/projects/{project.id}",
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(description="Complete Label Studio Pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--job_id", type=str, default=None, help="Custom job ID")
    parser.add_argument("--project_title", type=str, default=None, help="Custom Label Studio project title")
    parser.add_argument("--label_config", type=str, default=None, help="Path to Label Studio XML config file")
    parser.add_argument("--delay", type=int, default=30, help="Delay in seconds before syncing storage (default: 30)")
    parser.add_argument("--skip_inference", action="store_true", help="Skip inference and use existing job data")
    
    args = parser.parse_args()
    
    # Load main config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    # Check if Label Studio is configured
    if 'label_studio' not in config or 'api' not in config.get('label_studio', {}):
        print("Error: Label Studio API configuration not found in config file")
        print("Please add the following to your config:")
        print("""
label_studio:
  upload_enabled: true
  bucket: "your-bucket"
  prefix: "labelstudio-jsons"
  api:
    url: "http://your-label-studio-url:8080"
    api_key: "your-api-key"
    gcp_credentials_path: "/path/to/credentials.json"
        """)
        return 1
    
    try:
        # Step 1: Run inference pipeline (unless skipped)
        if not args.skip_inference:
            job_info = run_inference_with_conversion(args.config, args.job_id)
        else:
            # Load existing job info
            job_id = args.job_id
            if not job_id:
                print("Error: --job_id is required when using --skip_inference")
                return 1
            
            job_info_path = os.path.join(config['output_folder'], f"label_studio_job_{job_id}.json")
            if not os.path.exists(job_info_path):
                print(f"Error: Job info file not found: {job_info_path}")
                return 1
            
            with open(job_info_path, 'r') as f:
                job_info = json.load(f)
            print(f"Loaded existing job info for job ID: {job_id}")
        
        # Load custom label config if provided
        label_config = None
        if args.label_config and os.path.exists(args.label_config):
            with open(args.label_config, 'r') as f:
                label_config = f.read()
        
        # Step 2 & 3: Create Label Studio project and set up storage
        label_studio_config = config['label_studio']['api']
        project_info = create_label_studio_project_with_storage(
            job_info=job_info,
            label_studio_config=label_studio_config,
            project_title=args.project_title,
            label_config=label_config,
            delay_seconds=args.delay
        )
        
        # Save complete pipeline info
        pipeline_info = {
            "job_info": job_info,
            "project_info": project_info,
            "pipeline_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config_used": args.config
        }
        
        pipeline_info_path = os.path.join(config['output_folder'], f"pipeline_info_{job_info['job_id']}.json")
        with open(pipeline_info_path, 'w') as f:
            json.dump(pipeline_info, f, indent=2, default=str)
        
        print("=== PIPELINE COMPLETED SUCCESSFULLY ===")
        print(f"Job ID: {job_info['job_id']}")
        print(f"Project ID: {project_info['project'].id}")
        print(f"Project URL: {project_info['project_url']}")
        print(f"GCS Folder: gs://{project_info['gcs_bucket']}/{project_info['gcs_prefix']}")
        print(f"Pipeline info saved to: {pipeline_info_path}")
        
        if 'error' in project_info:
            print(f"Warning: {project_info['error']}")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main()) 