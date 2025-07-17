from label_studio_sdk.converter.brush import image2rle
import os
import numpy as np
from PIL import Image
from typing import List, Dict, Any, Optional, Tuple
import json
import yaml
from mindtrace.storage.gcs import GCSStorageHandler


def detections_to_label_studio(dict_format):
    """
    Convert list of detection dictionaries into Label Studio pre-annotations.
    
    Args:
        dict_format: List of dicts, where each dict represents one image with:
            - 'image_path': path to the image
            - 'bboxes': list of bbox dicts with 'x', 'y', 'width', 'height', 'confidence', 'class_name'
            - 'masks': list of mask file paths
            - 'mask_classes': list of class names for masks (same length as masks)
    Returns:
        List[dict] — a list of Label Studio "result" entries
    """
    
    all_annotations = []
    
    for image_data in dict_format:
        image_annotations = []
        
        if 'masks' in image_data and image_data['masks']:
            mask_paths = image_data['masks']
            mask_classes = image_data.get('mask_classes', [])
            
            for j, mask_path in enumerate(mask_paths):
                try:
                    rle, width, height = image2rle(mask_path)
                    
                    if not rle:
                        print(f"No rle found for mask: {mask_path}")
                        continue
                    
                    cls = mask_classes[j] if j < len(mask_classes) else "object"
                    
                    mask_ann = {
                        "image_rotation": 0,
                        "value": {"format": "rle", "rle": rle, "brushlabels": [cls]},
                        "from_name": "brush",
                        "to_name": "image",
                        "type": "brushlabels",
                    }
                    image_annotations.append(mask_ann)
                except Exception as e:
                    raise Exception(f"Error saving mask: {e}")
        
        if 'bboxes' in image_data and image_data['bboxes']:
            for bbox_data in image_data['bboxes']:
                try:
                    x = bbox_data['x']
                    y = bbox_data['y']
                    width = bbox_data['width']
                    height = bbox_data['height']
                    confidence = float(bbox_data['confidence'])
                    class_name = bbox_data['class_name']
                    
                    rect_annotation = {
                        "from_name": "bbox",
                        "to_name": "image",
                        "type": "rectanglelabels",
                        "image_rotation": 0,
                        "value": {
                            "x": x,
                            "y": y,
                            "width": width,
                            "height": height,
                            "rotation": 0,
                            "rectanglelabels": [class_name],
                            "score": confidence,
                        },
                    }
                    image_annotations.append(rect_annotation)
                except Exception as e:
                    raise Exception(f"Error saving bounding box: {e}")
        
        all_annotations.extend(image_annotations)
    
    return all_annotations


def parse_yolo_box_file(box_file_path: str, img_width: int, img_height: int, id2label: dict) -> List[Dict[str, Any]]:
    """
    Parse a YOLO format box file and convert directly to Label Studio format.
    
    Args:
        box_file_path: Path to the YOLO .txt file
        img_width: Width of the original image
        img_height: Height of the original image
    
    Returns:
        List of bounding box dictionaries with 'x', 'y', 'width', 'height', 'confidence', 'class_name' keys
    """
    bboxes = []
    
    if not os.path.exists(box_file_path):
        return bboxes
    
    try:
        with open(box_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) >= 5:
                    class_id = int(parts[0])
                    center_x = float(parts[1])
                    center_y = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])
                    confidence = float(parts[5])
                    
                    x = ((center_x - width / 2) / img_width) * 100
                    y = ((center_y - height / 2) / img_height) * 100
                    width_percent = (width / img_width) * 100
                    height_percent = (height / img_height) * 100
                    
                    bbox = {
                        'x': x,
                        'y': y,
                        'width': width_percent,
                        'height': height_percent,
                        'confidence': confidence,
                        'class_name': id2label[class_id]
                    }
                    bboxes.append(bbox)
    
    except Exception as e:
        print(f"Error parsing box file {box_file_path}: {e}")
    
    return bboxes


def extract_masks_from_pixel_values(mask_path: str, class_mapping: Optional[Dict[int, str]] = None) -> List[Tuple[str, str]]:
    """
    Extract individual class masks from a single mask image where pixel values represent class IDs.
    
    Args:
        mask_path: Path to the mask PNG file
        class_mapping: Optional mapping from class_id to class_name
    
    Returns:
        List of tuples (temp_mask_path, class_name) for each unique class in the mask
    """
    masks = []
    
    if not os.path.exists(mask_path):
        return masks
    
    try:
        mask_img = Image.open(mask_path)
        mask_array = np.array(mask_img)
        
        unique_classes = np.unique(mask_array)
        unique_classes = unique_classes[unique_classes > 0]
        
        for class_id in unique_classes:
            binary_mask = (mask_array == class_id).astype(np.uint8) * 255
            
            base_name = os.path.splitext(os.path.basename(mask_path))[0]
            temp_mask_path = f"/tmp/{base_name}_class_{class_id}.png"
            
            temp_mask_img = Image.fromarray(binary_mask, mode='L')
            temp_mask_img.save(temp_mask_path)
            
            print('--------------------------------------',class_mapping, class_id)
            if class_mapping and class_id in class_mapping:
                class_name = class_mapping[class_id]
            else:
                class_name = f"class_{class_id}"
            
            masks.append((temp_mask_path, class_name))
    
    except Exception as e:
        print(f"Error extracting masks from {mask_path}: {e}")
    
    return masks


def create_label_studio_mapping(gcs_path_mapping, output_folder, combined_mapping_file, job_id):
    """
    Create a mapping file that combines GCS paths with inference output paths
    for easy Label Studio configuration.
    
    Args:
        gcs_path_mapping: Dictionary containing GCS bucket and files mapping
        output_folder: Path to the inference output folder
        combined_mapping_file: Path where to save the combined mapping file
        job_id: Unique job identifier
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
            "image_source": "gcs",
            "gcs_bucket": gcs_path_mapping.get("bucket", ""),
            "gcs_prefix": gcs_path_mapping.get("prefix", "")
        }
    }
    
    with open(combined_mapping_file, 'w') as f:
        json.dump(mapping, f, indent=2)


def gather_detections_from_folders(
    output_folder: str,
    class_mapping: Optional[Dict[int, str]] = None,
    mask_task_names: Optional[List[str]] = None,
    box_task_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Gather detection data from the folder structure created by infer_folder.py.
    
    Args:
        output_folder: Root folder containing images/, boxes/, raw_masks/ subfolders
        class_mapping: Optional mapping from class_id to class_name
        box_task_names: List of box task names to process (e.g., ['zone_segmentation'])
        mask_task_names: List of mask task names to process (e.g., ['zone_segmentation'])
    
    Returns:
        List of detection dictionaries ready for detections_to_label_studio
    """
    detections = []
    
    images_folder = os.path.join(output_folder, "images")
    boxes_folder = os.path.join(output_folder, "boxes")
    raw_masks_folder = os.path.join(output_folder, "raw_masks")
    
    if not os.path.exists(images_folder):
        print(f"Images folder not found: {images_folder}")
        return detections
    
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
    image_files = [f for f in os.listdir(images_folder) 
                   if f.lower().endswith(image_extensions)]
    
    for image_file in image_files:
        image_name = os.path.splitext(image_file)[0]
        image_path = os.path.join(images_folder, image_file)
        
        try:
            with Image.open(image_path) as img:
                img_width, img_height = img.size
        except Exception as e:
            print(f"Error getting dimensions for {image_path}: {e}")
            continue

        bboxes = []
        masks = []
        mask_classes = []
        
        if box_task_names:
            for task_name in box_task_names:
                id2label_path = os.path.join(boxes_folder, task_name, "id2label.yaml")
                with open(id2label_path, 'r') as f:
                    id2label = yaml.safe_load(f)
                task_box_folder = os.path.join(boxes_folder, task_name)
                box_file_path = os.path.join(task_box_folder, f"{image_name}.txt")
                bboxes.extend(parse_yolo_box_file(box_file_path, img_width, img_height, id2label))
        
        if mask_task_names:
            for task_name in mask_task_names:
                id2label_path = os.path.join(raw_masks_folder, task_name, "id2label.yaml")
                with open(id2label_path, 'r') as f:
                    id2label = yaml.safe_load(f)
                task_mask_folder = os.path.join(raw_masks_folder, task_name)
                mask_file_path = os.path.join(task_mask_folder, f"{image_name}.png")
                
                if os.path.exists(mask_file_path):
                    class_masks = extract_masks_from_pixel_values(mask_file_path, class_mapping=id2label)
                    for temp_mask_path, class_name in class_masks:
                        print('--------------------------------------',class_name)
                        masks.append(temp_mask_path)
                        mask_classes.append(class_name)
        
        detection = {
            'image_path': image_path,
            'bboxes': bboxes,
            'masks': masks,
            'mask_classes': mask_classes
        }
        
        detections.append(detection)
    
    return detections


def create_label_studio_tasks(
    output_folder: str,
    class_mapping: Optional[Dict[int, str]] = None,
    mask_task_names: Optional[List[str]] = None,
    image_url_prefix: str = ""
) -> List[Dict[str, Any]]:
    """
    Create Label Studio tasks from the inference output folder structure.
    
    Args:
        output_folder: Root folder containing images/, boxes/, raw_masks/ subfolders
        class_mapping: Optional mapping from class_id to class_name
        mask_task_names: List of mask task names to process
        image_url_prefix: Prefix to add to image paths for Label Studio (e.g., GCS URL)
    
    Returns:
        List of Label Studio task dictionaries
    """
    detections = gather_detections_from_folders(output_folder, class_mapping, mask_task_names)
    annotations = detections_to_label_studio(detections)
    
    tasks = []
    current_image = None
    current_annotations = []
    
    for annotation in annotations:
        task = {
            "data": {
                "image": current_image or "placeholder_image_path"
            },
            "annotations": [
                {
                    "result": [annotation]
                }
            ]
        }
        tasks.append(task)
    
    return tasks


def export_to_label_studio_json(
    output_folder: str,
    export_path: str,
    class_mapping: Optional[Dict[int, str]] = None,
    mask_task_names: Optional[List[str]] = None
) -> bool:
    """
    Export inference results to Label Studio JSON format.
    
    Args:
        output_folder: Root folder containing inference results
        export_path: Path to save the Label Studio JSON file
        class_mapping: Optional mapping from class_id to class_name
        mask_task_names: List of mask task names to process
    
    Returns:
        True if export successful, False otherwise
    """
    try:
        detections = gather_detections_from_folders(output_folder, class_mapping, mask_task_names)
        annotations = detections_to_label_studio(detections)
        
        export_data = {
            "annotations": annotations,
            "metadata": {
                "source_folder": output_folder,
                "export_timestamp": str(np.datetime64('now')),
                "total_images": len(detections),
                "total_annotations": len(annotations)
            }
        }
        
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"Exported {len(annotations)} annotations to {export_path}")
        return True
    
    except Exception as e:
        print(f"Error exporting to Label Studio JSON: {e}")
        return False


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
    mask_task_names: list = None,
    box_task_names: list = None
) -> list:
    """Create individual Label Studio JSON files for each image with GCS URLs."""
    os.makedirs(output_dir, exist_ok=True)
    
    detections = gather_detections_from_folders(
        output_folder=output_folder,
        class_mapping=class_mapping,
        mask_task_names=mask_task_names,
        box_task_names=box_task_names
    )
    
    if "gcs_paths" in gcs_mapping:
        gcs_files = gcs_mapping.get("gcs_paths", {}).get("files", {})
        gcs_bucket = gcs_mapping.get("gcs_paths", {}).get("bucket", "")
    else:
        gcs_files = gcs_mapping.get("files", {})
        gcs_bucket = gcs_mapping.get("bucket", "")
    
    filename_to_gcs = {}
    for local_filename, gcs_path in gcs_files.items():
        filename_to_gcs[local_filename] = f"gs://{gcs_bucket}/{gcs_path}"
    
    print(f"GCS mapping contains {len(filename_to_gcs)} files:")
    for filename, gcs_url in filename_to_gcs.items():
        print(f"  {filename} -> {gcs_url}")
    
    annotations = detections_to_label_studio(detections)
    
    created_files = []
    annotation_index = 0
    
    for detection in detections:
        local_filename = os.path.basename(detection['image_path'])
        gcs_url = filename_to_gcs.get(local_filename)
        
        if not gcs_url:
            print(f"Skipping {local_filename} - no GCS URL available")
            num_bboxes = len(detection.get('bboxes', []))
            num_masks = len(detection.get('masks', []))
            total_annotations = num_bboxes + num_masks
            annotation_index += total_annotations
            continue
        
        try:
            with Image.open(detection['image_path']) as img:
                original_width, original_height = img.size
        except Exception as e:
            raise Exception(f"Failed to get image dimensions for {detection['image_path']}: {e}")
        
        num_bboxes = len(detection.get('bboxes', []))
        num_masks = len(detection.get('masks', []))
        total_annotations = num_bboxes + num_masks
        
        image_annotations = []
        for i in range(total_annotations):
            if annotation_index < len(annotations):
                annotation = annotations[annotation_index].copy()
                
                annotation.pop('original_width', None)
                annotation.pop('original_height', None)
                
                if annotation.get('type') == 'rectanglelabels' and 'value' in annotation:
                    value = annotation['value']
                
                if 'from_name' not in annotation:
                    if annotation.get('type') == 'rectanglelabels':
                        annotation['from_name'] = 'bbox'
                    elif annotation.get('type') == 'brushlabels':
                        annotation['from_name'] = 'brush'
                
                if 'to_name' not in annotation:
                    annotation['to_name'] = 'image'
                
                image_annotations.append(annotation)
                annotation_index += 1
        
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
        
        base_name = os.path.splitext(local_filename)[0]
        json_filename = f"{base_name}.json"
        json_path = os.path.join(output_dir, json_filename)
        
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
    """Upload multiple Label Studio JSON files to GCS using the configured path structure."""
    gcs_handler = GCSStorageHandler(
        bucket_name=gcs_config['bucket'],
        credentials_path=credentials_path
    )
    
    uploaded_urls = []
    
    for local_json_path in local_json_files:
        filename = os.path.basename(local_json_path)
        remote_path = f"{gcs_config['prefix']}/{job_id}/{filename}"
        
        try:
            gcs_url = gcs_handler.upload(local_json_path, remote_path)
            uploaded_urls.append(gcs_url)
            print(f"Uploaded {filename} to: {gcs_url}")
        except Exception as e:
            print(f"Error uploading {filename}: {e}")
    
    return uploaded_urls