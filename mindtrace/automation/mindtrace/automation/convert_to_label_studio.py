#!/usr/bin/env python3
"""
Script to convert inference output from infer_folder.py to Label Studio format.
"""

import os
import argparse
import json
import uuid
import yaml
import numpy as np
from PIL import Image
from pathlib import Path
from mindtrace.storage.gcs import GCSStorageHandler
from label_studio.utils import (
    gather_detections_from_folders,
    export_to_label_studio_json,
    detections_to_label_studio
)


def load_gcs_mapping(output_folder):
    """Load GCS path mapping if available."""
    gcs_mapping_file = os.path.join(output_folder, 'gcs_paths.json')
    label_studio_mapping_file = os.path.join(output_folder, 'label_studio_mapping.json')
    
    if os.path.exists(label_studio_mapping_file):
        with open(label_studio_mapping_file, 'r') as f:
            return json.load(f)
    elif os.path.exists(gcs_mapping_file):
        with open(gcs_mapping_file, 'r') as f:
            return {"gcs_paths": json.load(f)}
    else:
        return None


def create_individual_label_studio_files_with_gcs(
    output_folder: str,
    gcs_mapping: dict,
    output_dir: str,
    class_mapping: dict = None,
    mask_task_names: list = None
) -> list:
    """
    Create individual Label Studio JSON files for each image with GCS URLs.
    
    Args:
        output_folder: Root folder containing inference results
        gcs_mapping: GCS path mapping dictionary
        output_dir: Directory to save individual JSON files
        class_mapping: Optional mapping from class_id to class_name
        mask_task_names: List of mask task names to process
    
    Returns:
        List of created JSON file paths
    """
    from label_studio.utils import gather_detections_from_folders, detections_to_label_studio
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Gather detections with local paths
    detections = gather_detections_from_folders(
        output_folder=output_folder,
        class_mapping=class_mapping,
        mask_task_names=mask_task_names
    )
    
    # Get GCS mapping info
    gcs_files = gcs_mapping.get("gcs_paths", {}).get("files", {})
    gcs_bucket = gcs_mapping.get("gcs_paths", {}).get("bucket", "")
    
    # Create a mapping from local filename to GCS URL
    filename_to_gcs = {}
    for local_filename, gcs_path in gcs_files.items():
        filename_to_gcs[local_filename] = f"gs://{gcs_bucket}/{gcs_path}"
    
    print(f"GCS mapping contains {len(filename_to_gcs)} files:")
    for filename, gcs_url in filename_to_gcs.items():
        print(f"  {filename} -> {gcs_url}")
    
    # Convert to Label Studio format
    annotations = detections_to_label_studio(detections)
    
    # Create individual files for each image
    created_files = []
    annotation_index = 0
    
    for detection in detections:
        local_filename = os.path.basename(detection['image_path'])
        gcs_url = filename_to_gcs.get(local_filename)
        
        # Only include images that have GCS URLs
        if not gcs_url:
            print(f"Skipping {local_filename} - no GCS URL available")
            # Skip annotations for this image
            num_bboxes = len(detection.get('bboxes', []))
            num_masks = len(detection.get('masks', []))
            total_annotations = num_bboxes + num_masks
            annotation_index += total_annotations
            continue
        
        # Get image dimensions for coordinate conversion
        try:
            with Image.open(detection['image_path']) as img:
                original_width, original_height = img.size
        except Exception as e:
            print(f"Error getting image dimensions: {e}")
            original_width, original_height = 640, 480  # Fallback
        
        # Count how many annotations this image generated
        num_bboxes = len(detection.get('bboxes', []))
        num_masks = len(detection.get('masks', []))
        total_annotations = num_bboxes + num_masks
        
        # Get annotations for this image and convert to percentages
        image_annotations = []
        for i in range(total_annotations):
            if annotation_index < len(annotations):
                annotation = annotations[annotation_index].copy()
                
                # Remove original_width and original_height if present
                annotation.pop('original_width', None)
                annotation.pop('original_height', None)
                
                # Convert absolute coordinates to percentages for bounding boxes
                if annotation.get('type') == 'rectanglelabels' and 'value' in annotation:
                    value = annotation['value']
                    if 'x' in value and 'y' in value and 'width' in value and 'height' in value:
                        # Convert from absolute pixels to percentages
                        value['x'] = (value['x'] / original_width) * 100
                        value['y'] = (value['y'] / original_height) * 100
                        value['width'] = (value['width'] / original_width) * 100
                        value['height'] = (value['height'] / original_height) * 100
                
                # Ensure the annotation has the required fields
                if 'from_name' not in annotation:
                    if annotation.get('type') == 'rectanglelabels':
                        annotation['from_name'] = 'bbox'
                    elif annotation.get('type') == 'brushlabels':
                        annotation['from_name'] = 'brush'
                
                if 'to_name' not in annotation:
                    annotation['to_name'] = 'image'
                
                image_annotations.append(annotation)
                annotation_index += 1
        
        # Create prediction for this image
        prediction = {
            "data": {
                "image": gcs_url
            },
            "predictions": [
                {
                    "result": image_annotations
                }
            ]
        }
        
        # Create filename for this image (use image name without extension + .json)
        base_name = os.path.splitext(local_filename)[0]
        json_filename = f"{base_name}.json"
        json_path = os.path.join(output_dir, json_filename)
        
        # Save individual JSON file
        with open(json_path, 'w') as f:
            json.dump(prediction, f, indent=2)
        
        created_files.append(json_path)
        print(f"Created JSON for {local_filename}: {json_path}")
    
    return created_files


def upload_label_studio_jsons_to_gcs(
    local_json_files: list,
    gcs_config: dict,
    job_id: str,
    credentials_path: str
) -> list:
    """
    Upload multiple Label Studio JSON files to GCS using the configured path structure.
    
    Args:
        local_json_files: List of paths to local JSON files
        gcs_config: GCS configuration from YAML
        job_id: Unique job ID for organizing uploads
        credentials_path: Path to GCS credentials file
    
    Returns:
        List of GCS URLs of the uploaded files
    """
    # Initialize GCS handler
    gcs_handler = GCSStorageHandler(
        bucket_name=gcs_config['bucket'],
        credentials_path=credentials_path
    )
    
    uploaded_urls = []
    
    for local_json_path in local_json_files:
        # Construct the remote path: {prefix}/{job_id}/filename
        filename = os.path.basename(local_json_path)
        remote_path = f"{gcs_config['prefix']}/{job_id}/{filename}"
        
        try:
            # Upload the file
            gcs_url = gcs_handler.upload(local_json_path, remote_path)
            uploaded_urls.append(gcs_url)
            print(f"Uploaded {filename} to: {gcs_url}")
        except Exception as e:
            print(f"Error uploading {filename}: {e}")
    
    return uploaded_urls


def main():
    parser = argparse.ArgumentParser(description="Convert inference output to Label Studio format")
    parser.add_argument("--input_folder", required=True, 
                       help="Path to the inference output folder (e.g., /home/joshua/Desktop/test_output)")
    parser.add_argument("--output_dir", required=True,
                       help="Directory to save individual JSON files")
    parser.add_argument("--config", 
                       help="Path to YAML config file for GCS upload settings")
    parser.add_argument("--mask_tasks", nargs="+", default=["zone_segmentation"],
                       help="List of mask task names to process (default: zone_segmentation)")
    parser.add_argument("--class_mapping", type=str, default=None,
                       help="Path to JSON file with class_id to class_name mapping")
    parser.add_argument("--use_gcs_paths", action="store_true",
                       help="Use GCS paths for images instead of local paths")
    parser.add_argument("--verbose", action="store_true",
                       help="Print detailed information about the conversion process")
    parser.add_argument("--job_id", type=str, default=None,
                       help="Custom job ID (if not provided, will generate UUID)")
    
    args = parser.parse_args()
    
    # Generate or use provided job ID
    job_id = args.job_id or str(uuid.uuid4())
    print(f"Using job ID: {job_id}")
    
    # Load config if provided
    config = None
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
            print(f"Loaded config from: {args.config}")
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1
    
    # Load class mapping if provided
    class_mapping = None
    if args.class_mapping and os.path.exists(args.class_mapping):
        try:
            with open(args.class_mapping, 'r') as f:
                class_mapping = json.load(f)
            print(f"Loaded class mapping: {class_mapping}")
        except Exception as e:
            print(f"Error loading class mapping: {e}")
    
    # Check if input folder exists
    if not os.path.exists(args.input_folder):
        print(f"Error: Input folder not found: {args.input_folder}")
        return 1
    
    # Load GCS mapping if requested
    gcs_mapping = None
    if args.use_gcs_paths:
        gcs_mapping = load_gcs_mapping(args.input_folder)
        if gcs_mapping:
            print("Found GCS path mapping, will use GCS URLs for images")
            if args.verbose:
                print(f"GCS bucket: {gcs_mapping.get('gcs_paths', {}).get('bucket', 'unknown')}")
                print(f"Number of GCS files: {len(gcs_mapping.get('gcs_paths', {}).get('files', {}))}")
        else:
            print("Warning: GCS path mapping not found, falling back to local paths")
    
    # List the structure of the input folder
    if args.verbose:
        print(f"Input folder structure:")
        for root, dirs, files in os.walk(args.input_folder):
            level = root.replace(args.input_folder, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files[:5]:  # Show first 5 files
                print(f"{subindent}{file}")
            if len(files) > 5:
                print(f"{subindent}... and {len(files) - 5} more files")
    
    # Convert based on whether we have GCS paths
    if args.use_gcs_paths and gcs_mapping:
        print("Creating individual Label Studio JSON files with GCS paths...")
        created_files = create_individual_label_studio_files_with_gcs(
            output_folder=args.input_folder,
            gcs_mapping=gcs_mapping,
            output_dir=args.output_dir,
            class_mapping=class_mapping,
            mask_task_names=args.mask_tasks
        )
        
        print(f"Created {len(created_files)} individual JSON files in {args.output_dir}")
        
        # Upload to GCS if config is provided
        if config and 'label_studio' in config and config['label_studio'].get('upload_enabled', False):
            try:
                gcs_config = config['label_studio']
                credentials_path = config['gcp']['credentials_file']
                
                uploaded_urls = upload_label_studio_jsons_to_gcs(
                    local_json_files=created_files,
                    gcs_config=gcs_config,
                    job_id=job_id,
                    credentials_path=credentials_path
                )
                
                print(f"Successfully uploaded {len(uploaded_urls)} Label Studio JSON files to GCS")
                
                # Save job info to output folder
                job_info = {
                    "job_id": job_id,
                    "gcs_urls": uploaded_urls,
                    "local_files": created_files,
                    "upload_timestamp": str(np.datetime64('now')),
                    "total_files": len(created_files),
                    "gcs_folder": f"gs://{gcs_config['bucket']}/{gcs_config['prefix']}/{job_id}/"
                }
                
                job_info_path = os.path.join(args.input_folder, f"label_studio_job_{job_id}.json")
                with open(job_info_path, 'w') as f:
                    json.dump(job_info, f, indent=2)
                
                print(f"Saved job info to: {job_info_path}")
                print(f"All files uploaded to GCS folder: {job_info['gcs_folder']}")
                
            except Exception as e:
                print(f"Error uploading to GCS: {e}")
                return 1
        
    else:
        # Use the original local path approach
        print(f"Gathering detections from {args.input_folder}...")
        detections = gather_detections_from_folders(
            output_folder=args.input_folder,
            class_mapping=class_mapping,
            mask_task_names=args.mask_tasks
        )
        
        print(f"Found {len(detections)} images with detections")
        
        if args.verbose:
            for i, detection in enumerate(detections[:3]):  # Show first 3
                print(f"  Image {i+1}: {os.path.basename(detection['image_path'])}")
                print(f"    Bounding boxes: {len(detection['bboxes'])}")
                print(f"    Masks: {len(detection['masks'])}")
                print(f"    Mask classes: {detection['mask_classes']}")
        
        # For local paths, we'll create individual files too
        print("Converting to Label Studio format...")
        annotations = detections_to_label_studio(detections)
        
        print(f"Generated {len(annotations)} Label Studio annotations")
        
        # Create individual files for local approach too
        os.makedirs(args.output_dir, exist_ok=True)
        created_files = []
        annotation_index = 0
        
        for detection in detections:
            local_filename = os.path.basename(detection['image_path'])
            
            # Count how many annotations this image generated
            num_bboxes = len(detection.get('bboxes', []))
            num_masks = len(detection.get('masks', []))
            total_annotations = num_bboxes + num_masks
            
            # Get annotations for this image
            image_annotations = []
            for i in range(total_annotations):
                if annotation_index < len(annotations):
                    image_annotations.append(annotations[annotation_index])
                    annotation_index += 1
            
            # Create prediction for this image with local path
            prediction = {
                "data": {
                    "image": detection['image_path']
                },
                "predictions": [
                    {
                        "result": image_annotations
                    }
                ]
            }
            
            # Create filename for this image
            base_name = os.path.splitext(local_filename)[0]
            json_filename = f"{base_name}.json"
            json_path = os.path.join(args.output_dir, json_filename)
            
            # Save individual JSON file
            with open(json_path, 'w') as f:
                json.dump(prediction, f, indent=2)
            
            created_files.append(json_path)
            
        print(f"Created {len(created_files)} individual JSON files in {args.output_dir}")
    
    return 0


if __name__ == "__main__":
    exit(main()) 