import os
import argparse
import yaml
from mindtrace.automation.modelling.inference import Pipeline, ExportType
from mindtrace.automation.download_images import ImageDownload

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Efficiently download images using database and GCS")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()
    
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
    downloader.get_data()

    # Run the inference
    pipeline = Pipeline(
        credentials_path=config['gcp']['credentials_file'],
        bucket_name=config['gcp']['weights_bucket'],
        base_folder=config['gcp']['base_folder'],
        local_models_dir="./tmp"
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
        else:
            print("Inference failed")
            
    else:
        print(f"Input folder not found: {config['download_path']}")
        print("Skipping folder inference test")
