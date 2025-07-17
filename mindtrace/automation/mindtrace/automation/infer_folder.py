import os
import argparse
import yaml
import json
import uuid
from pathlib import Path
from mindtrace.automation.modelling.inference import Pipeline, ExportType
from mindtrace.automation.download_images import ImageDownload


def create_label_studio_mapping(gcs_path_mapping, output_folder, combined_mapping_file, job_id):
    """
    Create a mapping file that combines GCS paths with inference output paths
    for easy Label Studio configuration.
    """
    mapping = {
        "job_id": job_id,
        "gcs_paths": gcs_path_mapping,
        "local_paths": {
            "images": os.path.join(output_folder, "images"),
            "boxes": os.path.join(output_folder, "boxes"),
            "raw_masks": os.path.join(output_folder, "raw_masks"),
            "visualizations": os.path.join(output_folder, "visualizations")
        },
        "label_studio_config": {
            "image_source": "gcs",  # or "local"
            "gcs_bucket": gcs_path_mapping.get("bucket", ""),
            "gcs_prefix": gcs_path_mapping.get("prefix", "")
        }
    }
    
    with open(combined_mapping_file, 'w') as f:
        json.dump(mapping, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Efficiently download images using database and GCS")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--job_id", type=str, default=None, help="Custom job ID (if not provided, will generate UUID)")
    args = parser.parse_args()
    
    # Generate or use provided job ID
    job_id = args.job_id or str(uuid.uuid4())
    print(f"Starting inference job with ID: {job_id}")
    
    with open(args.config) as f:
        config = yaml.safe_load(f)
        
    # Get the data from the database
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
    
    # Download images and capture GCS paths
    print("Downloading images and capturing GCS paths...")
    gcs_path_mapping = downloader.get_data_with_gcs_paths()
    
    # Save GCS path mapping to JSON file
    gcs_mapping_file = os.path.join(config.get('download_path', 'downloads'), 'gcs_paths.json')
    with open(gcs_mapping_file, 'w') as f:
        json.dump(gcs_path_mapping, f, indent=2)
    print(f"Saved GCS path mapping to: {gcs_mapping_file}")

    # Run the inference
    pipeline = Pipeline(
        credentials_path=config['gcp']['credentials_file'],
        bucket_name=config['gcp']['weights_bucket'],
        base_folder=config['gcp']['base_folder'],
        local_models_dir="./tmp",
        overwrite_masks=config['overwrite_masks']
    )

    # Load the pipeline
    pipeline.load_pipeline(
        task_name=config['task_name'],
        version=config['version'],
        inference_list=config['inference_list']
    )

    if os.path.exists(config['download_path']):
        # Convert string export types to ExportType enum values
        export_types = {}
        for task_name, export_type_str in config['inference_list'].items():
            if export_type_str == "mask":
                export_types[task_name] = ExportType.MASK
            elif export_type_str == "bounding_box":
                export_types[task_name] = ExportType.BOUNDING_BOX

        # Run the inference
        summary = pipeline.run_inference_on_path(
            input_path=config['download_path'],
            output_folder=config['output_folder'],
            export_types=export_types,
            threshold=config['threshold'],
            save_visualizations=config['save_visualizations']
        )

        if summary and summary.get('processed_images', 0) > 0:
            print("Inference completed successfully")
            
            # Create a combined mapping file with both GCS paths and inference results
            combined_mapping_file = os.path.join(config['output_folder'], 'label_studio_mapping.json')
            create_label_studio_mapping(
                gcs_path_mapping=gcs_path_mapping,
                output_folder=config['output_folder'],
                combined_mapping_file=combined_mapping_file,
                job_id=job_id
            )
            print(f"Created Label Studio mapping file: {combined_mapping_file}")
            
            # If Label Studio upload is enabled, automatically run the conversion
            if config.get('label_studio', {}).get('upload_enabled', False):
                print(f"Label Studio upload is enabled, running conversion with job ID: {job_id}")
                
                # Import and run the conversion function
                try:
                    import subprocess
                    import sys
                    
                    # Construct the conversion command
                    conversion_cmd = [
                        sys.executable, "-m", "convert_to_label_studio",
                        "--input_folder", config['output_folder'],
                        "--output_dir", os.path.join(config['output_folder'], f"label_studio_jsons_{job_id}"),
                        "--config", args.config,
                        "--use_gcs_paths",
                        "--job_id", job_id,
                        "--verbose"
                    ]
                    
                    # Add mask tasks if specified
                    if config.get('mask_tasks'):
                        conversion_cmd.extend(["--mask_tasks"] + config['mask_tasks'])
                    
                    print(f"Running conversion command: {' '.join(conversion_cmd)}")
                    result = subprocess.run(conversion_cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        print("Label Studio conversion and upload completed successfully")
                        if result.stdout:
                            print("Conversion output:", result.stdout)
                    else:
                        print(f"Label Studio conversion failed with return code {result.returncode}")
                        if result.stderr:
                            print("Error output:", result.stderr)
                
                except Exception as e:
                    print(f"Error running Label Studio conversion: {e}")
            
        else:
            print("Inference failed")
            
    else:
        print(f"Input folder not found: {config['download_path']}")
        print("Skipping folder inference test")
