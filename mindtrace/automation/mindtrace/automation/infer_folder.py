import os
import argparse
import yaml
import json
import uuid
import glob
import random
from pathlib import Path
# from mindtrace.automation.modelling.inference import Pipeline, ExportType
from mindtrace.automation.modelling.sfz_pipeline import SFZPipeline, ExportType
from mindtrace.automation.modelling.laser_pipeline import LaserPipeline
from mindtrace.automation.download_images import ImageDownload
from mindtrace.automation.label_studio.utils import create_label_studio_mapping
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig


def run_inference(config_path: str, custom_job_id: str = None, pipeline_type: str = 'sfz'):
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
        image_paths = []
        
        # --- START of new logic ---

        # 1. Handle sampling
        sampling_config = config.get('sampling', {})
        if sampling_config.get('enabled', False):
            print("Local sampling enabled.")
            images_per_folder = sampling_config.get('images_per_folder', 1)
            
            try:
                subfolders = [f.path for f in os.scandir(input_path) if f.is_dir()]
            except FileNotFoundError:
                print(f"Error: The specified local_image_path does not exist: {input_path}")
                return None

            if not subfolders: # if no subfolders, sample from root
                print(f"No subdirectories found in {input_path}. Sampling from the root directory.")
                subfolders = [input_path]
            
            sampled_images = []
            image_extensions = ["*.jpg", "*.jpeg", "*.png"]

            for folder in subfolders:
                all_images_in_folder = []
                for ext in image_extensions:
                    all_images_in_folder.extend(glob.glob(os.path.join(folder, ext)))
                
                if not all_images_in_folder:
                    print(f"No images found in folder: {folder}")
                    continue

                # take all if requested number is higher
                num_to_sample = min(images_per_folder, len(all_images_in_folder))
                print(f"Sampling {num_to_sample} image(s) from {folder}")
                
                # random sampling
                sampled_images.extend(random.sample(all_images_in_folder, num_to_sample))
            image_paths = sampled_images
        else:
            # fallback to old logic if sampling is not enabled
            image_extensions = ["*.jpg", "*.jpeg", "*.png"]
            for ext in image_extensions:
                # Search recursively to find all images under the path
                image_paths.extend(glob.glob(os.path.join(input_path, '**', ext), recursive=True))
        
        print(f"Found {len(image_paths)} images after sampling.")

        # 2. Handle Label Studio deduplication
        label_studio_config = config.get('label_studio')
        if image_paths and label_studio_config and label_studio_config.get('upload_enabled'):
            print("Checking for existing images in Label Studio...")
            
            api_config = label_studio_config['api']
            try:
                label_studio = LabelStudio(
                    LabelStudioConfig(
                        url=api_config['url'],
                        api_key=api_config['api_key'],
                        gcp_creds=api_config.get('gcp_credentials_path')
                    )
                )
                project_prefix = label_studio_config.get('project', {}).get('title')

                existing_gcs_paths = label_studio.get_all_existing_gcs_paths(project_prefix)
                existing_filenames = {os.path.basename(path) for path in existing_gcs_paths}
                print(f"Found {len(existing_filenames)} unique filenames in Label Studio projects.")

                original_count = len(image_paths)
                image_paths = [p for p in image_paths if os.path.basename(p) not in existing_filenames]
                filtered_count = original_count - len(image_paths)
                
                print(f"\nDEDUPLICATION SUMMARY:")
                print(f"  Images after sampling: {original_count}")
                print(f"  Images already in Label Studio: {filtered_count}")
                print(f"  Images remaining for inference: {len(image_paths)}\n")

            except Exception as e:
                print(f"Warning: Could not check for existing images in Label Studio: {e}")
                print("Continuing without deduplication...")
        
        if not image_paths:
            print(f"No images to process after sampling and deduplication.")
            return None
        
        gcs_path_mapping = {f"file://{os.path.abspath(p)}": os.path.basename(p) for p in image_paths}


    else:
        raise ValueError(f"Unsupported data_source: {data_source}")

    if pipeline_type == 'sfz':
        pipeline = SFZPipeline(
        credentials_path=config['gcp']['credentials_file'],
        bucket_name=config['gcp']['weights_bucket'],
        base_folder=config['gcp']['base_folder'],
        local_models_dir="./tmp",
        overwrite_masks=config['overwrite_masks']
    )
    elif pipeline_type == 'laser':
        pipeline = LaserPipeline(
            credentials_path=config['gcp']['credentials_file'],
            bucket_name=config['gcp']['weights_bucket'],
            base_folder=config['gcp']['base_folder'],
            local_models_dir="./tmp",
            overwrite_masks=config['overwrite_masks']
        )
    else:
        raise ValueError(f"Unsupported pipeline type: {pipeline_type}")
    
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
            save_visualizations=config['save_visualizations'],
            image_list=list(gcs_path_mapping.keys()) if data_source == 'local' else None
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
