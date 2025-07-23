import yaml
from pathlib import Path
import re
import argparse
from label_studio.label_studio_api import LabelStudio, LabelStudioConfig 
import json

def main(config_path: str, project_id: int = None):
    """
    Export Label Studio project to datalake format and publish it.
    
    Args:
        config_path: Path to the config file
        project_id: Optional project ID override
    """
    print(f"Loading config from: {config_path}")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize Label Studio client
    label_studio = LabelStudio(
        LabelStudioConfig(
            url=config['label_studio']['api']['url'],
            api_key=config['label_studio']['api']['api_key'],
            gcp_creds=config['label_studio']['api']['gcp_credentials_path']
        )
    )
    
    output_dir = Path(config['output_folder'])
    download_path = Path(config['download_path'])
    
    # Get datalake config
    datalake_config = config.get('datalake', {})
    dataset_name = datalake_config.get('dataset_name', f"defect_detection_dataset_{project_id}")
    version = datalake_config.get('version', "1.0.0")
    description = datalake_config.get('description', f"Defect detection dataset exported from Label Studio project {project_id}")
    new_dataset = datalake_config.get('new_dataset', True)
    
    # Get mask generation config
    mask_generation_config = config.get('mask_generation', {})
    labelstudio_config = mask_generation_config.get('labelstudio', {})
    sam_config_section = mask_generation_config.get('sam', {})
    labelstudio_all_masks = labelstudio_config.get('generate_all_masks', False)
    sam_all_masks = sam_config_section.get('generate_all_masks', False)
    
    # Prepare SAM config with mask generation settings
    sam_config = config.get('sam', {})
    if sam_config:
        # Add mask generation config to SAM config
        sam_config['mask_generation'] = mask_generation_config
    
    # Extract detection and segmentation classes from Label Studio interface config
    interface_config = config['label_studio']['interface_config']
    detection_classes = []
    segmentation_classes = []

    # Extract classes from RectangleLabels sections (detection)
    rectangle_sections = re.findall(r'<RectangleLabels.*?>(.*?)</RectangleLabels>', interface_config, re.DOTALL)
    for section in rectangle_sections:
        matches = re.findall(r'<Label value="([^"]+)"[^>]*?/>', section)
        detection_classes.extend(matches)

    # Extract classes from PolygonLabels sections (segmentation)
    polygon_sections = re.findall(r'<PolygonLabels.*?>(.*?)</PolygonLabels>', interface_config, re.DOTALL)
    for section in polygon_sections:
        matches = re.findall(r'<Label value="([^"]+)"[^>]*?/>', section)
        segmentation_classes.extend(matches)

    # Validate that we found some classes
    if not detection_classes:
        print("No detection classes found")
    if not segmentation_classes:
        print("No segmentation classes found")

    print(f"Testing datalake export for project {project_id}")
    print(f"Output directory: {output_dir}")
    print(f"Download path: {download_path}")
    print(f"Dataset name: {dataset_name}")
    print(f"Version: {version}")
    print(f"Operation: {'Creating new' if new_dataset else 'Updating existing'} dataset")
    print(f"Detection classes (from RectangleLabels): {detection_classes}")
    print(f"Segmentation classes (from PolygonLabels): {segmentation_classes}")
    print(f"Using datalake GCP credentials: {datalake_config.get('gcp_creds_path')}")
    print(f"Label Studio all masks generation: {'Enabled' if labelstudio_all_masks else 'Disabled'}")
    print(f"SAM all masks generation: {'Enabled' if sam_all_masks else 'Disabled'}")
    
    try:
        result = label_studio.convert_and_publish_to_datalake(
            project_id=project_id,
            output_dir=output_dir,
            download_path=download_path,
            dataset_name=dataset_name,
            version=version,
            train_split=0.8,
            test_split=0.2,
            download_images=True,
            generate_masks=True,
            all_masks=labelstudio_all_masks,
            description=description,
            hf_token=datalake_config.get('hf_token'),
            gcp_creds_path=datalake_config.get('gcp_creds_path'),
            new_dataset=new_dataset,
            detection_classes=detection_classes,
            segmentation_classes=segmentation_classes,
            sam_config=sam_config  # Pass SAM config with mask generation settings
        )
        
        print("\nExport completed successfully!")
        print(f"Dataset directory: {result['dataset_dir']}")
        print(f"Manifest file: {result['manifest']}")
        print("\nSplit statistics:")
        print(f"Train: {result['splits']['train']} images")
        print(f"Test: {result['splits']['test']} images")
        
        # Print class mapping
        print("\nClass mapping:")
        for class_type, mapping in result['class_mapping'].items():
            print(f"{class_type}:")
            print(json.dumps(mapping, indent=2))
        
        # Print file summary instead of listing every file
        dataset_dir = Path(result['dataset_dir'])
        train_images = len(list(dataset_dir.glob("splits/train/images/*")))
        train_masks = len(list(dataset_dir.glob("splits/train/masks/*")))
        test_images = len(list(dataset_dir.glob("splits/test/images/*")))
        test_masks = len(list(dataset_dir.glob("splits/test/masks/*")))
        
        print("\nFile Summary:")
        print(f"Train split: {train_images} images, {train_masks} masks")
        print(f"Test split: {test_images} images, {test_masks} masks")
        print(f"Total files: {train_images + train_masks + test_images + test_masks}")
        
    except Exception as e:
        print(f"❌ Error during export: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Label Studio project to datalake")
    parser.add_argument("--config", type=str, help="Path to config file", 
                       default="configs/images_config.yaml")  # This path is relative to where we run the script
    parser.add_argument("--project-id", type=int, help="Label Studio project ID to export", required=True)
    
    args = parser.parse_args()
    main(args.config, args.project_id) 