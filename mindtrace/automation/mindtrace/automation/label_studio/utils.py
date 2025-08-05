from label_studio_sdk.converter.brush import image2rle
from tqdm import tqdm
import os
import numpy as np
from PIL import Image
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
import json
import yaml
import cv2
from mindtrace.storage.gcs import GCSStorageHandler
from collections import defaultdict
import random
import numpy as np
from sklearn.model_selection import train_test_split, StratifiedShuffleSplit
import torch
from torch.utils.data import random_split
from pathlib import Path


def detections_to_label_studio(
    dict_format: List[Dict], mask_from_name: str, mask_tool_type: str, polygon_epsilon_factor: float = 0.005
):
    """
    Convert list of detection dictionaries into Label Studio pre-annotations.
    
    Args:
        dict_format: List of dicts, where each dict represents one image with:
            - 'image_path': path to the image
            - 'bboxes': list of bbox dicts with 'x', 'y', 'width', 'height', 'confidence', 'class_name'
            - 'masks': list of mask file paths
            - 'mask_classes': list of class names for masks (same length as masks)
        mask_from_name: The 'name' of the label tag in Label Studio config (e.g., 'label').
        mask_tool_type: The tool type from LS config, 'PolygonLabels' or 'BrushLabels'.
        polygon_epsilon_factor: Epsilon factor for polygon simplification.
    Returns:
        List[dict] — a list of Label Studio "result" entries
    """
    
    all_annotations = []
    
    for image_data in dict_format:
        image_annotations = []
        
        try:
            with Image.open(image_data['image_path']) as img:
                img_width, img_height = img.size
        except Exception as e:
            print(f"Error getting image dimensions for {image_data['image_path']}: {e}. Skipping mask processing for this image.")
            continue

        if 'masks' in image_data and image_data['masks']:
            mask_paths = image_data['masks']
            mask_classes = image_data.get('mask_classes', [])
            
            for j, mask_path in enumerate(mask_paths):
                cls = mask_classes[j] if j < len(mask_classes) else "object"

                # Skip empty mask paths (indicates no mask file)
                if not mask_path:
                    print(f"Skipping empty mask for class: {cls}")
                    continue

                if mask_tool_type == 'BrushLabels':
                    try:
                        rle, _, _ = image2rle(mask_path)
                        
                        if not rle:
                            print(f"No rle found for mask: {mask_path}")
                            continue
                        
                        mask_ann = {
                            "original_width": img_width,
                            "original_height": img_height,
                            "image_rotation": 0,
                            "value": {"format": "rle", "rle": rle, "brushlabels": [cls]},
                            "from_name": mask_from_name,
                            "to_name": "image",
                            "type": 'brushlabels',
                        }
                        image_annotations.append(mask_ann)
                    except Exception as e:
                        raise Exception(f"Error saving brush mask: {e}")

                elif mask_tool_type == 'PolygonLabels':
                    try:
                        polygons = mask_to_polygons(
                            mask_path, img_width, img_height, epsilon_factor=polygon_epsilon_factor
                        )
                        for points in polygons:
                            polygon_ann = {
                                "original_width": img_width,
                                "original_height": img_height,
                                "image_rotation": 0,
                                "value": {
                                    "points": points,
                                    "polygonlabels": [cls]
                                },
                                "from_name": mask_from_name,
                                "to_name": "image",
                                "type": "polygonlabels",
                            }
                            image_annotations.append(polygon_ann)
                    except Exception as e:
                        raise Exception(f"Error saving polygon: {e}")
        
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
                        "original_width": img_width,
                        "original_height": img_height,
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
                    
                    x = ((center_x - width / 2) / img_width) * 100
                    y = ((center_y - height / 2) / img_height) * 100
                    width_percent = (width / img_width) * 100
                    height_percent = (height / img_height) * 100
                    
                    bbox = {
                        'x': x,
                        'y': y,
                        'width': width_percent,
                        'height': height_percent,
                        'class_name': id2label.get(class_id, f"class_{class_id}")
                    }

                    if len(parts) > 5:
                        bbox['confidence'] = float(parts[5])

                    bboxes.append(bbox)
    
    except Exception as e:
        print(f"Error parsing box file {box_file_path}: {e}")
    
    return bboxes


def mask_to_polygons(
    mask_path: str, img_width: int, img_height: int, epsilon_factor: float = 0.005
) -> List[List[List[float]]]:
    """
    Converts a binary mask image to a list of polygons in Label Studio format.
    Args:
        mask_path: Path to the binary mask file.
        img_width: Width of the original image for normalization.
        img_height: Height of the original image for normalization.
        epsilon_factor: Factor to determine the approximation accuracy for polygon simplification.
                        Smaller values result in more points.
    Returns:
        A list of polygons, where each polygon is a list of [x, y] points (0-100).
    """
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return []

    # Using RETR_EXTERNAL to get only external contours
    # Using CHAIN_APPROX_SIMPLE to save memory
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    polygons = []
    for contour in contours:
        if contour.shape[0] < 3:  # A polygon needs at least 3 points
            continue
        
        # Approximate the contour to reduce points
        epsilon = epsilon_factor * cv2.arcLength(contour, True)
        approx_contour = cv2.approxPolyDP(contour, epsilon, True)

        if approx_contour.shape[0] < 3:
            continue
        
        # Normalize points to 0-100 range for Label Studio
        polygon = [[(p[0][0] / img_width) * 100, (p[0][1] / img_height) * 100] for p in approx_contour]
        polygons.append(polygon)
        
    return polygons


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
            
            class_name = class_mapping.get(class_id, f"class_{class_id}")
            
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
    class_mapping: Optional[Dict[str, Dict[int, str]]] = None,
    mask_task_names: Optional[List[str]] = None,
    box_task_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Gather detection data from the folder structure created by infer_folder.py.
    
    Args:
        output_folder: Root folder containing images/, boxes/, raw_masks/ subfolders
        class_mapping: A dictionary mapping task names to their id2label dictionaries.
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
                id2label_str_keys = class_mapping.get(task_name) if class_mapping else None
                if not id2label_str_keys:
                    print(f"Warning: No class mapping found for box task '{task_name}'. Skipping.")
                    continue
                id2label = {int(k): v for k, v in id2label_str_keys.items()}
                task_box_folder = os.path.join(boxes_folder, task_name)
                box_file_path = os.path.join(task_box_folder, f"{image_name}.txt")
                bboxes.extend(parse_yolo_box_file(box_file_path, img_width, img_height, id2label))
        
        if mask_task_names:
            for task_name in mask_task_names:
                id2label_str_keys = class_mapping.get(task_name) if class_mapping else None
                if not id2label_str_keys:
                    print(f"Warning: No class mapping found for mask task '{task_name}'. Skipping.")
                    continue
                id2label = {int(k): v for k, v in id2label_str_keys.items()}
                task_mask_folder = os.path.join(raw_masks_folder, task_name)
                mask_file_path = os.path.join(task_mask_folder, f"{image_name}.png")
                
                if os.path.exists(mask_file_path):
                    class_masks = extract_masks_from_pixel_values(mask_file_path, class_mapping=id2label)
                    for temp_mask_path, class_name in class_masks:
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
    mask_from_name: str,
    mask_tool_type: str,
    class_mapping: Optional[Dict[int, str]] = None,
    mask_task_names: Optional[List[str]] = None,
    image_url_prefix: str = "",
    polygon_epsilon_factor: float = 0.005,
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
    annotations = detections_to_label_studio(
        detections, mask_from_name, mask_tool_type, polygon_epsilon_factor=polygon_epsilon_factor
    )
    
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
    mask_from_name: str,
    mask_tool_type: str,
    class_mapping: Optional[dict] = None,
    mask_task_names: Optional[list] = None,
    box_task_names: Optional[list] = None,
    polygon_epsilon_factor: float = 0.005,
) -> list:
    """Create individual Label Studio JSON files for each image with GCS URLs."""
    os.makedirs(output_dir, exist_ok=True)
    
    detections = gather_detections_from_folders(
        output_folder=output_folder,
        class_mapping=class_mapping,
        mask_task_names=mask_task_names,
        box_task_names=box_task_names
    )
    
    filename_to_gcs = {}
    gcs_path_data = gcs_mapping.get("gcs_paths", gcs_mapping)

    if 'files' in gcs_path_data and 'bucket' in gcs_path_data:
        gcs_files = gcs_path_data.get("files", {})
        gcs_bucket = gcs_path_data.get("bucket", "")
        for local_filename, gcs_path in gcs_files.items():
             filename_to_gcs[local_filename] = f"gs://{gcs_bucket}/{gcs_path}"
    else:
        for local_path, gcs_url in gcs_mapping.items():
            filename_to_gcs[os.path.basename(local_path)] = gcs_url

    created_files = []
    
    for detection in tqdm(detections, desc="Creating Label Studio JSON files"):
        local_filename = os.path.basename(detection['image_path'])
        gcs_url = filename_to_gcs.get(local_filename)

        if not gcs_url:
            print(f"Skipping {local_filename} - no GCS URL available")
            continue
        
        image_annotations = detections_to_label_studio(
            [detection],
            mask_from_name=mask_from_name,
            mask_tool_type=mask_tool_type,
            polygon_epsilon_factor=polygon_epsilon_factor,
        )
        
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
    
    for local_json_path in tqdm(local_json_files, desc="Uploading Label Studio JSONs to GCS"):
        filename = os.path.basename(local_json_path)
        remote_path = f"{gcs_config['prefix']}/{job_id}/{filename}"
        
        try:
            gcs_url = gcs_handler.upload(local_json_path, remote_path)
            uploaded_urls.append(gcs_url)
        except Exception as e:
            print(f"Error uploading {filename}: {e}")
    
    return uploaded_urls


def split_dataset(
    data: list,
    train_split: float = 0.7,
    val_split: float = 0.2,
    test_split: float = 0.1,
    seed: int = 42
) -> dict:
    """Split a dataset into train/val/test sets using random splitting.
    
    Args:
        data: List of items to split (e.g. Label Studio task JSONs)
        train_split: Fraction of data for training (default: 0.7)
        val_split: Fraction of data for validation (default: 0.2)
        test_split: Fraction of data for testing (default: 0.1)
        seed: Random seed for reproducible splits (default: 42)
    
    Returns:
        Dict with 'splits' and 'stats'
    """
    if abs(train_split + val_split + test_split - 1.0) > 1e-6:
        raise ValueError("Train/val/test splits must sum to 1.0")
    
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
    
    data_list = list(data)
    total = len(data_list)
    
    train_size = int(total * train_split)
    val_size = int(total * val_split)
    test_size = total - train_size - val_size  
    train_data, val_data, test_data = random_split(
        data_list,
        lengths=[train_size, val_size, test_size],
        generator=torch.Generator().manual_seed(seed)
    )
    splits = {
        'train': [data_list[i] for i in train_data.indices],
        'val': [data_list[i] for i in val_data.indices],
        'test': [data_list[i] for i in test_data.indices]
    }
    
    stats = {
        'total': total,
        'train': len(splits['train']),
        'val': len(splits['val']),
        'test': len(splits['test'])
    }
    
    return {
        'splits': splits,
        'stats': stats
    }


def create_dataset_structure(base_dir: Path, splits: List[str] = ['train', 'test']) -> None:
    """Create directory structure for dataset."""
    base_dir = Path(base_dir)
    
    splits_dir = base_dir / "splits"
    for split in splits:
        (splits_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (splits_dir / split / "masks").mkdir(parents=True, exist_ok=True)


def create_manifest(
    base_dir: Union[str, Path],
    name: str,
    version: str,
    splits: Dict[str, List[str]],
    description: str = "",
    detection_classes: Optional[List[str]] = None,
    segmentation_classes: Optional[List[str]] = None
) -> None:
    """Create a manifest file for the dataset."""
    base_dir = Path(base_dir)
    
    manifest = {
        "name": name,
        "version": version,
        "description": description,
        "data_type": "image",
        "outputs": [
            {
                "name": "bboxes",
                "type": "detection",
                "classes": detection_classes or [],
                "required": False
            },
            {
                "name": "zones",
                "type": "image_segmentation",
                "classes": segmentation_classes or [],
                "required": False
            }
        ],
        "splits": {}
    }
    
    for split_name, files in splits.items():
        if not files or split_name == 'val':
            continue
            
        data_files = {}
        
        for file_path in files:
            path = Path(file_path)
            if path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp']:
                data_files[path.name] = str(path)
        
        manifest["splits"][split_name] = {
            "data_files": data_files,
            "annotations": f"annotations_v{version}.json",
            "removed": []
        }
    
    manifest_path = base_dir / f"manifest_v{version}.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    readme_content = f"""# {name} Dataset v{version}

{description}

## Structure
- splits/"""
    
    for split_name in manifest["splits"].keys():
        readme_content += f"""
  - {split_name}/ ({len(manifest["splits"][split_name]["data_files"])} files)
    - images/
    - masks/
    - annotations_v{version}.json"""
    
    readme_content += """

## Detection Classes (RectangleLabels)
"""
    readme_content += json.dumps(detection_classes or [], indent=2)
    
    readme_content += """

## Segmentation Classes (PolygonLabels)
"""
    readme_content += json.dumps(segmentation_classes or [], indent=2)
    
    with open(base_dir / "README.md", 'w') as f:
        f.write(readme_content)


def organize_files_into_splits(
    base_dir: Path,
    split_assignments: Dict[str, List[str]],
    source_images_dir: Path,
    source_masks_dir: Optional[Path] = None
) -> Dict[str, List[str]]:
    """Move files into split directories.
    
    Args:
        base_dir: Base directory for dataset
        split_assignments: Dictionary mapping split names to lists of image filenames
        source_images_dir: Directory containing source images
        source_masks_dir: Optional directory containing source masks
    
    Returns:
        Dictionary mapping split names to lists of moved file paths (absolute paths)
    """
    import shutil
    
    base_dir = Path(base_dir)
    source_images_dir = Path(source_images_dir)
    if source_masks_dir:
        source_masks_dir = Path(source_masks_dir)
    
    moved_files = {split: [] for split in split_assignments.keys()}
    
    for split_name, filenames in split_assignments.items():
        split_images_dir = base_dir / "splits" / split_name / "images"
        split_masks_dir = base_dir / "splits" / split_name / "masks"
        
        for filename in filenames:
            # Move image
            src_image = source_images_dir / filename
            dst_image = split_images_dir / filename
            shutil.move(src_image, dst_image)
            moved_files[split_name].append(str(dst_image.absolute()))
            
            # Move mask if it exists
            if source_masks_dir:
                mask_name = f"{Path(filename).stem}_mask.png"
                src_mask = source_masks_dir / mask_name
                if src_mask.exists():
                    dst_mask = split_masks_dir / mask_name
                    shutil.move(src_mask, dst_mask)
                    moved_files[split_name].append(str(dst_mask.absolute()))
    
    return moved_files
