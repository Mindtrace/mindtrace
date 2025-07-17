import os
import argparse
import yaml
import json
import uuid
from pathlib import Path
from mindtrace.automation.modelling.inference import Pipeline, ExportType
from mindtrace.automation.download_images import ImageDownload
from mindtrace.automation.label_studio.utils import create_label_studio_mapping


def run_inference(config_path: str, custom_job_id: str = None):
    """Run inference pipeline and return job information for Label Studio integration."""
    job_id = custom_job_id or str(uuid.uuid4())
    print(f"Starting inference job with ID: {job_id}")
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    downloader = ImageDownload(
        database=os.getenv('DATABASE_NAME'),
        user=os.getenv('DATABASE_USERNAME'),
        password=os.getenv('DATABASE_PASSWORD'),
        host=os.getenv('DATABASE_HOST_NAME'),
        port=os.getenv('DATABASE_PORT'),
        gcp_credentials_path=config['gcp']['credentials_file'],
        gcp_bucket=config['gcp']['data_bucket'],
        local_download_path=config.get('download_path', 'downloads'),
        config=config
    )
    
    print("Downloading images and capturing GCS paths...")
    gcs_path_mapping = downloader.get_data_with_gcs_paths()
    
    gcs_mapping_file = os.path.join(config.get('download_path', 'downloads'), 'gcs_paths.json')
    with open(gcs_mapping_file, 'w') as f:
        json.dump(gcs_path_mapping, f, indent=2)
    print(f"Saved GCS path mapping to: {gcs_mapping_file}")

    pipeline = Pipeline(
        credentials_path=config['gcp']['credentials_file'],
        bucket_name=config['gcp']['weights_bucket'],
        base_folder=config['gcp']['base_folder'],
        local_models_dir="./tmp",
        overwrite_masks=config['overwrite_masks']
    )

    pipeline.load_pipeline(
        task_name=config['task_name'],
        version=config['version'],
        inference_list=config['inference_list']
    )

    if os.path.exists(config['download_path']):
        export_types = {}
        for task_name, export_type_str in config['inference_list'].items():
            if export_type_str == "mask":
                export_types[task_name] = ExportType.MASK
            elif export_type_str == "bounding_box":
                export_types[task_name] = ExportType.BOUNDING_BOX

        summary = pipeline.run_inference_on_path(
            input_path=config['download_path'],
            output_folder=config['output_folder'],
            export_types=export_types,
            threshold=config['threshold'],
            save_visualizations=config['save_visualizations']
        )

        if summary and summary.get('processed_images', 0) > 0:
            print("Inference completed successfully")
            
            combined_mapping_file = os.path.join(config['output_folder'], 'label_studio_mapping.json')
            create_label_studio_mapping(
                gcs_path_mapping=gcs_path_mapping,
                output_folder=config['output_folder'],
                combined_mapping_file=combined_mapping_file,
                job_id=job_id
            )
            print(f"Created Label Studio mapping file: {combined_mapping_file}")
            
            return {
                "job_id": job_id,
                "gcs_path_mapping": gcs_path_mapping,
                "inference_summary": summary,
                "config": config,
                "gcs_folder": f"gs://{config.get('label_studio', {}).get('bucket', '')}/{config.get('label_studio', {}).get('prefix', '')}/{job_id}/"
            }
            
        else:
            print("Inference failed")
            return None
            
    else:
        print(f"Input folder not found: {config['download_path']}")
        print("Skipping folder inference test")
        return None
