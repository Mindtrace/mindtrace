import os
import argparse
import yaml
import json
import uuid
import glob
from pathlib import Path
# from mindtrace.automation.modelling.inference import Pipeline, ExportType
from mindtrace.automation.modelling.sfz_pipeline import SFZPipeline, ExportType
from mindtrace.automation.download_images import ImageDownload
from mindtrace.automation.label_studio.utils import create_label_studio_mapping


def run_inference(config_path: str, custom_job_id: str = None):
    """Run inference pipeline and return job information for Label Studio integration."""
    job_id = custom_job_id or str(uuid.uuid4())
    print(f"Starting inference job with ID: {job_id}")
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    if 'inference_list' in config:
        # Only auto-generate mask_tasks if not explicitly provided in config
        if 'mask_tasks' not in config:
            config['mask_tasks'] = [
                task for task, task_type in config['inference_list'].items() if task_type == 'mask'
            ]
        config['bounding_box_tasks'] = [
            task for task, task_type in config['inference_list'].items() if task_type == 'bounding_box'
        ]

    data_source = config.get('data_source', 'gcp')
    gcs_path_mapping = {}
    input_path = None

    if data_source == 'gcp':
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
        input_path = config.get('download_path', 'downloads')
        
        gcs_mapping_file = os.path.join(input_path, 'gcs_paths.json')
        with open(gcs_mapping_file, 'w') as f:
            json.dump(gcs_path_mapping, f, indent=2)
        print(f"Saved GCS path mapping to: {gcs_mapping_file}")

    elif data_source == 'local':
        input_path = config['local_image_path']
        image_extensions = ["*.jpg", "*.jpeg", "*.png"]
        image_paths = []
        for ext in image_extensions:
            image_paths.extend(glob.glob(os.path.join(input_path, ext)))
        
        if not image_paths:
            print(f"No images found in {input_path}")
            return None
        
        # For local files, we create a mapping from the file path to a URI
        gcs_path_mapping = {f"file://{os.path.abspath(p)}": os.path.basename(p) for p in image_paths}

    else:
        raise ValueError(f"Unsupported data_source: {data_source}")

    pipeline = SFZPipeline(
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
    
    # Get class mappings from the loaded models
    class_mappings = {}
    print("\n--- DEBUG: RETRIEVING CLASS MAPPINGS FROM MODELS ---")
    for task_name in config['inference_list']:
        model_info = pipeline.get_model_info(task_name)
        if model_info and 'id2label' in model_info:
            class_mappings[task_name] = model_info['id2label']
            print(f"Task '{task_name}': Found id2label map with {len(model_info['id2label'])} classes.")
            print(json.dumps(model_info['id2label'], indent=2))
        else:
            print(f"Task '{task_name}': No id2label map found.")
    print("----------------------------------------------------\n")


    if os.path.exists(input_path):
        export_types = {}
        for task_name, export_type_str in config['inference_list'].items():
            if export_type_str == "mask":
                export_types[task_name] = ExportType.MASK
            elif export_type_str == "bounding_box":
                export_types[task_name] = ExportType.BOUNDING_BOX

        summary = pipeline.run_inference_on_path(
            input_path=input_path,
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
            
            result = {
                "job_id": job_id,
                "gcs_path_mapping": gcs_path_mapping,
                "inference_summary": summary,
                "config": config,
                "class_mappings": class_mappings,
            }

            if data_source == 'gcp':
                 result["gcs_folder"] = f"gs://{config.get('label_studio', {}).get('bucket', '')}/{config.get('label_studio', {}).get('prefix', '')}/{job_id}/"
            
            return result
            
        else:
            print("Inference failed")
            return None
            
    else:
        print(f"Input folder not found: {input_path}")
        print("Skipping folder inference test")
        return None
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Efficiently download images using database and GCS")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()

    job_id = str(uuid.uuid4())
    run_inference(args.config, job_id)
