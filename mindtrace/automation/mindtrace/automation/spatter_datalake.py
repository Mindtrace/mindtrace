import os
import argparse
import yaml
import uuid
import numpy as np
import cv2
from PIL import Image
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.cloud import storage
import requests
import sys
import shutil 
from collections import defaultdict
import random
from tqdm import tqdm
import re
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig
from mtrix.datalake import Datalake
from mindtrace.automation.cropping import crop_zones, get_updated_key
import torch
try:
    import torch
    from mtrix.models import SegmentAnything
    SAM_AVAILABLE = True
except ImportError:
    SAM_AVAILABLE = False

def download_image_gs(task, save_path):
    gcs_client = storage.Client()
    url = task['data']['image']
    try:
        if url.startswith("gs://"):
            bucket_name, blob_path = url[5:].split('/', 1)
            bucket = gcs_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            fname = blob_path.split('/')[-1]
            fp = os.path.join(save_path, fname)
            blob.download_to_filename(fp)
            print(f"[SUCCESS] {url} → {fname}")
            return fname
        else:
            print(f"[SKIPPED] Not a gs:// URL: {url}")
            return f"[SKIPPED] {url}"
    except Exception as e:
        print(f"[ERROR] {url} => {e}")
        return f"[ERROR] {url} => {e}"

def download_image_http(task, save_path):
    url = task['data']['image']
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            print(f"[SUCCESS] {url}")
            fname = '_'.join(url.split('?')[0].split('/')[-2:])
            fp = os.path.join(save_path, fname)
            with open(fp, 'wb') as f:
                f.write(resp.content)
            return fname
        else:
            print(f"[FAILED {resp.status_code}] {url}")
            return f"[FAILED {resp.status_code}] {url}"
    except Exception as e:
        return f"[ERROR] {url} => {e}"

def download_image(task, save_path):
    url = task['data']['image']
    if url.startswith('gs://'):
        return download_image_gs(task, save_path)
    else:
        return download_image_http(task, save_path)

def labelstudio_to_yolo(labels, image_width, image_height):
    yolo_labels = []
    for label in labels:
        # Handle nested format
        original_label = label  # Keep original for rectanglelabels
        if 'value' in label:
            label = label['value']
        
        x = label['x']
        y = label['y']
        w = label['width']
        h = label['height']
        
        x_center = (x + w / 2) / 100.0
        y_center = (y + h / 2) / 100.0
        width_norm = w / 100.0
        height_norm = h / 100.0
        
        yolo_labels.append((x_center, y_center, width_norm, height_norm))
    return yolo_labels

def _update_image_project_map(map_path: str, mapping_updates: dict):
    """Safely update an on-disk mapping of image filename -> project_id.
    """
    existing = {}
    if os.path.exists(map_path):
        try:
            with open(map_path, 'r') as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    existing.update(mapping_updates or {})
    os.makedirs(os.path.dirname(map_path), exist_ok=True)
    with open(map_path, 'w') as f:
        json.dump(existing, f)


def _derive_original_from_crop(filename: str) -> str | None:
    """If filename follows the cropping convention '<base>_<i>.<ext>',
    return '<base>.<ext>' else None.
    """
    name, ext = os.path.splitext(filename)
    if '_' not in name:
        return None
    base, suffix = name.rsplit('_', 1)
    if suffix.isdigit():
        return base + ext
    return None

def download_data_yolo(
    json_path, 
    images_save_path, 
    labels_save_path, 
    zone_masks_save_path,
    workers, 
    zone_class_names,
    keep_small_spatter,
    separate_class,
    ignore_holes=True,
    delete_empty_masks=True,
    
):
    os.makedirs(images_save_path, exist_ok=True)
    os.makedirs(labels_save_path, exist_ok=True)
    os.makedirs(zone_masks_save_path, exist_ok=True)

    # Create spatter class mapping from config
    spatter_class_mapping = {name: str(i) for i, name in enumerate(config['spatter_class_names'])}

    with open(json_path, 'r') as f:
        data = json.load(f)

    # --- Segregate URLs ---
    gs_urls = []
    http_tasks = []
    for task in data:
        url = task['data']['image']
        if url.startswith('gs://'):
            gs_urls.append(url)
        else:
            http_tasks.append(task)
    
    print(f"Total images to download: {len(gs_urls)} GCS, {len(http_tasks)} HTTP")

    # --- Batch Download from GCS ---
    if gs_urls:
        print(f"Starting GCS download of {len(gs_urls)} images...")
        gcs_client = storage.Client()

        def download_gs_file(url):
            try:
                bucket_name, blob_path = url[5:].split('/', 1)
                bucket = gcs_client.bucket(bucket_name)
                blob = bucket.blob(blob_path)
                file_path = os.path.join(images_save_path, os.path.basename(blob_path))
                if os.path.exists(file_path):
                    print(f"File already exists: {file_path}")
                    return
                blob.download_to_filename(file_path)
            except Exception as e:
                print(f"[ERROR] {url} => {e}")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            list(tqdm(executor.map(download_gs_file, gs_urls), total=len(gs_urls), desc="Downloading GCS files"))

    # --- Batch Download from HTTP ---
    if http_tasks:
        print(f"Starting HTTP download of {len(http_tasks)} images...")

        def download_http_file(task, session):
            url = task['data']['image']
            try:
                resp = session.get(url, timeout=30)
                if resp.status_code == 200:
                    base_fname = '_'.join(url.split('?')[0].split('/')[-2:])
                    fp = os.path.join(images_save_path, base_fname)
                    with open(fp, 'wb') as f:
                        f.write(resp.content)
                else:
                    print(f"[FAILED {resp.status_code}] {url}")
            except Exception as e:
                print(f"[ERROR] {url} => {e}")
        
        with requests.Session() as session:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(download_http_file, task, session) for task in http_tasks]
                for future in tqdm(as_completed(futures), total=len(http_tasks), desc="Downloading HTTP files"):
                    future.result()

    print("All downloads complete. Processing annotations...")

    # Process zone masks with progress bar
    for d in tqdm(data, desc="Processing zone masks"):
        image_local_path = os.path.join(images_save_path, d['data']['image'].split('/')[-1])
        if not os.path.exists(image_local_path):
            continue
            
        image = Image.open(image_local_path)
        w, h = image.size
        mask = np.zeros((h, w), dtype=np.uint8)
        idx2class = {i: n for i, n in enumerate(zone_class_names)}
        class2idx = {n: i for i, n in enumerate(zone_class_names)}
        
        for an in d['annotations']:
            hole_polygons = []
            normal_polygons = []
            
            for result in an['result']:
                if result['type'] != 'polygonlabels':
                    continue

                class_name = result['value']['polygonlabels'][0]
                points = (np.array(result['value']['points']) * np.array([w, h]) / 100).astype(np.int32)
                points = points.reshape((-1, 1, 2)) 

                if class_name == 'Hole':
                    hole_polygons.append(points)
                else:
                    normal_polygons.append((points, class2idx[class_name]))
            
            # Sort by class_id to ensure consistent drawing order
            normal_polygons.sort(key=lambda p: p[1])
            
            for contour, class_id in normal_polygons:
                cv2.fillPoly(mask, [contour], color=class_id)

            if not ignore_holes:
                for contour in hole_polygons:
                    cv2.fillPoly(mask, [contour], color=class2idx['Hole'])
        
        mask_save_path = os.path.join(
            zone_masks_save_path,
            d['data']['image'].split('/')[-1].replace('.jpg', '_mask.png')
        )
        cv2.imwrite(mask_save_path, mask)

    # Process spatter annotations with progress bar
    processed_filenames = []  
    for task in tqdm(data, desc="Processing spatter annotations"):
        image_url = task['data']['image']
        if image_url.startswith('gs://'):
            base_fname = image_url.split('/')[-1]
        else:
            base_fname = '_'.join(image_url.split('?')[0].split('/')[-2:])

        image_path = os.path.join(images_save_path, base_fname)
        label_path = os.path.join(labels_save_path, base_fname.rsplit('.', 1)[0] + '.txt')
        
        if not os.path.exists(image_path):
            print(f"Image not found after download: {image_path}, skipping annotation processing.")
            continue
        
        processed_filenames.append(base_fname)
            
        img = Image.open(image_path)
        img_width, img_height = img.size

        labels = []
        for a in task.get('annotations', []):
            for r in a.get('result', []):
                if 'value' in r and 'rectanglelabels' in r['value']:
                    rectangle_labels = [label.lower() for label in r['value']['rectanglelabels']]
                    
                    # Check for spatter labels based on configuration
                    has_spatter = 'spatter' in rectangle_labels
                    has_small_spatter = 'small_spatter' in rectangle_labels

                    if has_spatter or (has_small_spatter and keep_small_spatter):
                        # If separate_class is False, treat small_spatter as spatter
                        if has_small_spatter and not separate_class:
                            modified_result = r.copy()
                            modified_result['value'] = r['value'].copy()
                            modified_result['value']['rectanglelabels'] = ['spatter']
                            labels.append(modified_result)
                        else:
                            labels.append(r['value'])

        if not labels:
            with open(label_path, 'w') as f:
                f.write('')
            continue

        conv = labelstudio_to_yolo(labels, img_width, img_height)
        l = ''
        for label, c in zip(labels, conv):
            # Handle nested format for rectanglelabels
            if 'value' in label:
                rectanglelabels = label['value']['rectanglelabels']
            else:
                rectanglelabels = label['rectanglelabels']
            class_name = rectanglelabels[0].lower()
            if class_name in spatter_class_mapping:
                class_id = int(spatter_class_mapping[class_name])

            l = l + str(class_id) + ' ' + str(c[0]) + ' ' + str(c[1]) + ' ' + str(c[2]) + ' ' + str(c[3]) + '\n'
        with open(label_path, 'w') as f:
            f.write(l)

    return processed_filenames

def generate_masks_from_boxes(images_dir, labels_dir, masks_save_path, device_id=None, spatter_class_names=None):
    if not SAM_AVAILABLE:
        print("torch or mtrix.models.SegmentAnything not found. Cannot generate masks.")
        sys.exit(1)
        
    # Auto-select best GPU if device_id is None
    if device_id is None:
        try:
            from mindtrace.automation.modelling.utils.gpu_selector import set_environment_for_best_gpu
            device_id = set_environment_for_best_gpu(min_memory_gb=8.0, max_utilization=70.0)
        except ImportError:
            print("GPU selector not available, using default cuda:0")
            device_id = 'cuda:0'
    
    device = torch.device(device_id)
    print(f"Loading SAM model to {device}...")
    model = SegmentAnything(model='vit_h', device=device)

    os.makedirs(masks_save_path, exist_ok=True)
    
    spatter_class_mapping = {name: str(i) for i, name in enumerate(spatter_class_names)}

    # Get total count for progress bar
    total_images = len([f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
    print(f"Found {total_images} images to process")

    with tqdm(total=total_images, desc="Generating masks from boxes") as pbar:
        for name in os.listdir(images_dir):
            if not name.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue

            image_path = os.path.join(images_dir, name)
            image = Image.open(image_path).convert("RGB")
            
            label_path = os.path.join(labels_dir, name.rsplit('.', 1)[0] + '.txt')
            if not os.path.exists(label_path):
                # Create empty mask if no label file
                mask_image = Image.new('L', image.size, 0)
                mask_image.save(os.path.join(masks_save_path, name.rsplit('.', 1)[0] + '_mask.png'), mode='L')
                pbar.update(1)
                continue

            with open(label_path, 'r') as f:
                label_string = f.readlines()

            img_width, img_height = image.size

            boxes_xyxy = []
            for line in label_string:
                line = line.strip().split()
                x_center, y_center, width, height = map(float, line[1:])
                
                x1 = (x_center - width / 2) * img_width
                y1 = (y_center - height / 2) * img_height
                x2 = (x_center + width / 2) * img_width
                y2 = (y_center + height / 2) * img_height

                boxes_xyxy.append([x1, y1, x2, y2])
            
            if not boxes_xyxy:
                mask_image = Image.new('L', image.size, 0)
                mask_image.save(os.path.join(masks_save_path, name.rsplit('.', 1)[0] + '_mask.png'), mode='L')
                pbar.update(1)
                continue

            model.set_image(np.array(image))
            
            combined_mask = np.zeros((img_height, img_width), dtype=np.uint8)
            for i, b in enumerate(boxes_xyxy):
                masks, _, _ = model.model.predict(box=np.array(b), multimask_output=False)
                mask = masks[0]
                class_id = int(label_string[i].strip().split()[0])
                combined_mask[mask] = class_id
                
            cv2.imwrite(os.path.join(masks_save_path, name.rsplit('.', 1)[0] + '_mask.png'), combined_mask)
            pbar.update(1)
            
    print("Mask generation complete.")

def train_test_split(base_dir, desired_ratio=0.2, project_image_map_path: str | None = None, project_split_overrides: dict | None = None):
    images_dir = os.path.join(base_dir, 'images')
    
    all_images = [f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    random.seed(42)
    random.shuffle(all_images)
    
    image_to_project = {}
    if project_image_map_path and os.path.exists(project_image_map_path):
        try:
            with open(project_image_map_path, 'r') as f:
                image_to_project = json.load(f)
        except Exception:
            image_to_project = {}

    overrides = project_split_overrides or {}
    overrides = {str(k): v for k, v in overrides.items()}  # normalize keys to str

    # Compute forced splits based on overrides
    forced_train = set()
    forced_test = set()

    for img in list(all_images):
        proj_id = image_to_project.get(img)
        if proj_id is None:
            # Try to map cropped images back to original
            orig = _derive_original_from_crop(img)
            if orig and orig in image_to_project:
                proj_id = image_to_project[orig]
        if proj_id is None:
            continue
        target_split = overrides.get(str(proj_id))
        if not target_split:
            continue
        if target_split == 'train':
            forced_train.add(img)
        elif target_split == 'test':
            forced_test.add(img)

    # Remaining pool after forced selections
    remaining = [f for f in all_images if f not in forced_train and f not in forced_test]

    total_images = len(all_images)
    target_test_size = int(total_images * desired_ratio)

    # Determine how many additional test images are needed
    additional_test_needed = max(0, target_test_size - len(forced_test))

    # Select for test from remaining
    random.shuffle(remaining)
    selected_test = set(remaining[:additional_test_needed])
    selected_train = set(remaining[additional_test_needed:])

    # Combine with forced sets
    test_set = set(forced_test) | selected_test
    train_set = set(forced_train) | selected_train

    print(f"Splitting {len(all_images)} images into {len(train_set)} train and {len(test_set)} test...")

    for split_name, image_set in [('train', train_set), ('test', test_set)]:
        print(f"\nProcessing {split_name} split...")
        for f in tqdm(image_set, desc=f"Moving {split_name} files"):
            base_filename, _ = os.path.splitext(f)

            source_image_path = os.path.join(images_dir, f)
            target_image_dir = os.path.join(images_dir, split_name)
            os.makedirs(target_image_dir, exist_ok=True)
            if os.path.exists(source_image_path):
                shutil.move(source_image_path, os.path.join(target_image_dir, f))
        
            labels_dir = os.path.join(base_dir, 'labels')
            if os.path.isdir(labels_dir):
                label_filename = base_filename + '.txt'
                source_label_path = os.path.join(labels_dir, label_filename)
                if os.path.exists(source_label_path):
                    target_label_dir = os.path.join(labels_dir, split_name)
                    os.makedirs(target_label_dir, exist_ok=True)
                    shutil.move(source_label_path, os.path.join(target_label_dir, label_filename))
            
           
            for mask_type in ['spatter_masks', 'zone_masks']:
                masks_dir = os.path.join(base_dir, mask_type)
                if os.path.isdir(masks_dir):
                    mask_filename = base_filename + '_mask.png'
                    source_mask_path = os.path.join(masks_dir, mask_filename)
                    if os.path.exists(source_mask_path):
                        target_mask_dir = os.path.join(masks_dir, split_name)
                        os.makedirs(target_mask_dir, exist_ok=True)
                        shutil.move(source_mask_path, os.path.join(target_mask_dir, mask_filename))

    print("Train-test split complete.")


def perform_cropping(base_dir, cropping_config_path, zone_class_mapping, save_updated_zone_masks=False, splits=['train', 'test']):
    print("Starting cropping process...")
    with open(cropping_config_path, 'r') as f:
        cropping_config = json.load(f)

    for split in splits:
        images_dir = os.path.join(base_dir, 'images', split)
        zone_masks_dir = os.path.join(base_dir, 'zone_masks', split)
        spatter_masks_dir = os.path.join(base_dir, 'spatter_masks', split)

        if not os.path.isdir(images_dir):
            continue

        for image_name in tqdm(os.listdir(images_dir), desc=f"Cropping {split} set"):
            if not image_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue

            image_path = os.path.join(images_dir, image_name)
            base_filename, ext = os.path.splitext(image_name)
            
            # Use regex to extract camera key from filename
            key = base_filename.split("-")[0]
            print(key)
            camera_key = get_updated_key(key)

            zone_mask_path = os.path.join(zone_masks_dir, base_filename + '_mask.png')
            spatter_mask_path = os.path.join(spatter_masks_dir, base_filename + '_mask.png')

            if not os.path.exists(zone_mask_path):
                print(f"Zone mask not found for {image_name}, skipping cropping.")
                continue

            img = cv2.imread(image_path)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            zone_mask = cv2.imread(zone_mask_path, cv2.IMREAD_GRAYSCALE)
            
            spatter_mask = None
            if os.path.exists(spatter_mask_path):
                spatter_mask = cv2.imread(spatter_mask_path, cv2.IMREAD_GRAYSCALE)

            crop_results = crop_zones(
                zone_masks=[torch.from_numpy(zone_mask)],
                imgs=[img],
                keys=[camera_key],
                cropping_config=cropping_config,
                reference_masks={},  
                zone_segmentation_class_mapping=zone_class_mapping,
                square_crop=True,
                image_names=[base_filename],
                spatter_masks=[spatter_mask] if spatter_mask is not None else None
            )

            if not crop_results['all_image_crops']:
                continue

            
            for i, (img_crop, zone_crop, spatter_crop) in enumerate(zip(
                crop_results['all_image_crops'], 
                crop_results['all_mask_crops'],
                crop_results['all_spatter_mask_crops']
            )):
                #Save cropped  image
                crop_img_name = f"{base_filename}_{i}{ext}"
                crop_img_path = os.path.join(images_dir, crop_img_name)
                # Convert back to BGR for saving with cv2
                cv2.imwrite(crop_img_path, cv2.cvtColor(img_crop, cv2.COLOR_RGB2BGR))

                # If spatter mask exists, crop and save it
                if spatter_crop is not None:
                    crop_spatter_mask_name = f"{base_filename}_{i}_mask.png"
                    crop_spatter_mask_path = os.path.join(spatter_masks_dir, crop_spatter_mask_name)
                   
                    cv2.imwrite(crop_spatter_mask_path, spatter_crop)

                if save_updated_zone_masks:
                    crop_zone_mask_name = f"{base_filename}_{i}_mask.png"
                    crop_zone_mask_path = os.path.join(zone_masks_dir, crop_zone_mask_name)
                    cv2.imwrite(crop_zone_mask_path, zone_crop.numpy())

    print("Cropping complete.")

def upload_to_huggingface_yolo(download_dir, huggingface_config, use_mask=False, clean_up=False, class_names=None, download=False):

    dataset_name = huggingface_config.get('dataset_name')
    version = huggingface_config.get('version')
    existing_dataset = huggingface_config.get('existing_dataset')
    existing_version = huggingface_config.get('existing_version')
    token = huggingface_config.get('token')
    gcp_creds_path = huggingface_config.get('gcp_creds_path')
    
    os.environ['HF_TOKEN'] = token
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_creds_path
    
    if existing_dataset is not None:
        missing_count = 0
        if download:
            datalake = Datalake(
                hf_token = token,    
                gcp_creds_path = gcp_creds_path,
                datalake_dir = download_dir
            )
            ds = datalake.get_dataset(
                dataset_name = existing_dataset,
                version = existing_version
            )

            print('Downloading dataset from datalake')
            datalake_train_path = os.path.join(download_dir, existing_dataset, 'splits', 'train')
            datalake_test_path = os.path.join(download_dir, existing_dataset, 'splits', 'test')
            
            for file in os.listdir(os.path.join(datalake_train_path, 'images')):
                image_path = os.path.join(datalake_train_path, 'images', file)
                mask_path = os.path.join(datalake_train_path, 'masks', file.replace('.jpg', '_mask.png'))

                if os.path.exists(mask_path) and os.path.exists(image_path):
                    new_image_path = os.path.join(download_dir, 'images', 'train', os.path.basename(image_path))
                    new_mask_path = os.path.join(download_dir, 'spatter_masks', 'train', os.path.basename(mask_path))
                    shutil.move(image_path, new_image_path)
                    shutil.move(mask_path, new_mask_path)
                else:
                    missing_count += 1

            for file in os.listdir(os.path.join(datalake_test_path, 'images')):
                image_path = os.path.join(datalake_test_path, 'images', file)
                mask_path = os.path.join(datalake_test_path, 'masks', file.replace('.jpg', '_mask.png'))

                if os.path.exists(mask_path) and os.path.exists(image_path):
                    shutil.move(image_path, os.path.join(download_dir, 'images', 'test', file))
                    shutil.move(mask_path, os.path.join(download_dir, 'spatter_masks', 'test', file.replace('.jpg', '_mask.png')))
                else:
                    missing_count += 1

            print(f"Missing count: {missing_count}")        
            shutil.rmtree(datalake_train_path)
            shutil.rmtree(datalake_test_path)
            shutil.rmtree(os.path.join(download_dir, existing_dataset))

    target_path = os.path.join(download_dir, dataset_name)
    source_images_train = os.path.join(download_dir, 'images', 'train')
    source_masks_train  = os.path.join(download_dir, 'spatter_masks', 'train')

    source_images_test = os.path.join(download_dir, 'images', 'test')
    source_masks_test  = os.path.join(download_dir, 'spatter_masks', 'test')

    os.makedirs(os.path.join(target_path, 'splits' ,'train', 'masks'), exist_ok=True)
    os.makedirs(os.path.join(target_path, 'splits', 'test', 'masks'), exist_ok=True)
    os.makedirs(os.path.join(target_path, 'splits', 'train', 'images'), exist_ok=True)
    os.makedirs(os.path.join(target_path, 'splits', 'test', 'images'), exist_ok=True)

    train_annotations = {}
    train_metadata = {}
    train_data_files = {}


    val_annotations = {}
    val_metadata = {}
    val_data_files = {}


    for i in os.listdir(source_images_train):
        train_annotations[i] = {
            'file_name' : i,
            'CameraIDX' : -1
        }
        train_data_files[i] = os.path.join(source_images_train, i)
        shutil.copy(os.path.join(source_images_train, i), os.path.join(target_path, 'splits', 'train', 'images', i))
        mask_name = i.rsplit('.', 1)[0] + '_mask.png'
        mask_src = os.path.join(source_masks_train, mask_name)
        train_annotations[i]['masks'] = mask_name
        train_data_files[mask_name] = os.path.join(target_path, 'splits', 'train', 'masks', mask_name)
        shutil.copy(mask_src, os.path.join(target_path, 'splits', 'train', 'masks', mask_name))
        
        train_metadata[i] = {"file_name": i, "metadata" : {'CameraIDX' : 'M'}}              

    for i in os.listdir(source_images_test):
        val_annotations[i] = {
            'file_name' : i,
            'CameraIDX' : -1
        }
        val_data_files[i] = os.path.join(source_images_test, i)
        shutil.copy(os.path.join(source_images_test, i), os.path.join(target_path,'splits',  'test', 'images', i))
        mask_name = i.rsplit('.', 1)[0] + '_mask.png'
        mask_src = os.path.join(source_masks_test, mask_name)
        val_annotations[i]['masks'] = mask_name
        val_data_files[mask_name] = os.path.join(target_path, 'splits', 'test', 'masks', mask_name)
        shutil.copy(mask_src, os.path.join(target_path, 'splits', 'test', 'masks', mask_name))

        val_metadata[i] = {"file_name": i, "metadata" : {'CameraIDX' : 'M'}}


    train_metadata = {'images': train_metadata}
    val_metadata = {'images': val_metadata}

    train_annotations = {'images': train_annotations}
    val_annotations = {'images': val_annotations}

    save_path = target_path

    with open(os.path.join(save_path,'splits',  'train', f'annotations_v{version}.json'), 'w') as f:
        json.dump(train_annotations, f)

    with open(os.path.join(save_path, 'splits', 'test', f'annotations_v{version}.json'), 'w') as f:
        json.dump(val_annotations, f)
        
    with open(os.path.join(save_path, 'splits', 'train', f'item_metadata_v{version}.json'), 'w') as f:
        json.dump(train_metadata, f)

    with open(os.path.join(save_path, 'splits', 'test', f'item_metadata_v{version}.json'), 'w') as f:
        json.dump(val_metadata, f)

    manifest_sample = {
        "name": dataset_name,
        "version": version,
        "data_type": "image",
        "incremental": True,  # What does incremental even mean ? 
        "description": 'V0',
        "outputs": [
            {
                "name": "masks",
                "type": "image_segmentation",
                "classes": class_names,
                "required": False
            },
            {
                "name" : "CameraIDX",
                "type" : "regression",
                "required" : False
            }


        ],
        "splits": {
            "train": {
                "data_files" : train_data_files,

            "annotations": f"annotations_v{version}.json",
            "item_metadata": f"item_metadata_v{version}.json",
            "removed": []
            },
            "test": {
                "data_files": val_data_files,

            "annotations": f"annotations_v{version}.json",
            "item_metadata": f"item_metadata_v{version}.json",
            "removed": []
            }
        }
    }

    with open(os.path.join(save_path, f'manifest_v{version}.json'), 'w') as f:
        json.dump(manifest_sample, f)
    
    print('Creating dataset', dataset_name, version)
    datalake = Datalake(
        hf_token = token,    
        gcp_creds_path = gcp_creds_path,
    )
    if dataset_name in datalake.list_datasets():
        datalake.update_dataset(
            src = os.path.join(download_dir, dataset_name),
            dataset_name = dataset_name,
            version = version,
        )
    else:
        datalake.create_dataset(
            source = os.path.join(download_dir, dataset_name),
            dataset_name = dataset_name,
            version = version,
        )
    datalake.publish_dataset(
        dataset_name = dataset_name,
        version = version,
    )

    if clean_up:
        shutil.rmtree(download_dir)


def process_label_studio_projects(project_ids, config, download_dir):
    """
    Runs the full data processing pipeline for a given list of Label Studio projects.
    """
    label_studio_config = config['label_studio']
    convert_box_to_mask = config.get('convert_box_to_mask', False)

    label_studio = LabelStudio(LabelStudioConfig(url=label_studio_config['api']['url'], api_key=label_studio_config['api']['api_key']))
    
    images_save_path = os.path.join(download_dir, 'images')
    labels_save_path = os.path.join(download_dir, 'labels')
    zone_masks_save_path = os.path.join(download_dir, 'zone_masks')
    os.makedirs(images_save_path, exist_ok=True)
    os.makedirs(labels_save_path, exist_ok=True)

    # Mapping file: image filename -> project_id
    project_image_map_path = os.path.join(download_dir, 'project_image_map.json')
    
    for proj_id in project_ids:
        export_path = os.path.join(download_dir, f"{proj_id}.json")
        print(f"Exporting project {proj_id} to {export_path}")
        label_studio.export_annotations(
            project_id=proj_id,
            export_type=label_studio_config['export_type'],
            export_location=export_path
        )
        
        processed_filenames = download_data_yolo(
            export_path, 
            images_save_path, 
            labels_save_path, 
            zone_masks_save_path,
            config['workers'], 
            config['zone_class_names'],
            keep_small_spatter=config.get('keep_small_spatter'),
            separate_class=config.get('separate_class'),
            ignore_holes=config.get('ignore_holes', True),
            delete_empty_masks=config.get('delete_empty_masks', True)
        )

        # Update mapping for originals
        _update_image_project_map(project_image_map_path, {fname: str(proj_id) for fname in processed_filenames})
    
    if convert_box_to_mask:
        print("\nStarting box to mask conversion...")
        masks_save_path = os.path.join(download_dir, 'spatter_masks')
        spatter_class_names = config.get('spatter_class_names')
        
        generate_masks_from_boxes(
            images_save_path, 
            labels_save_path, 
            masks_save_path,
            device_id=None,
            spatter_class_names=spatter_class_names
        )

    return download_dir


def run_pipeline(config, base_dir):
    """Unified pipeline without mode selection (no merging or incremental)."""
    print("--- Starting pipeline ---")
    
    label_studio_config = config['label_studio']
    label_studio = LabelStudio(LabelStudioConfig(url=label_studio_config['api']['url'], api_key=label_studio_config['api']['api_key']))

    # Build project name -> id mapping for convenience
    project_names = label_studio_config['project_list']
    name_to_id = {}
    for name in project_names:
        p = label_studio.get_project_by_name(name)
        name_to_id[name] = p.id
    project_ids = [name_to_id[name] for name in project_names]

    if not project_ids:
        print("No projects found in 'project_list'. Exiting.")
        sys.exit(0)

    # Process Label Studio projects into base_dir
    processed_dir = process_label_studio_projects(project_ids, config, base_dir)
    final_dir_to_process = processed_dir

    # Prepare project split overrides (accept names only; validate against project_list)
    overrides_cfg = config.get('project_split_overrides', {})
    overrides_by_id = {}
    for key, split in overrides_cfg.items():
        key_str = str(key)
        if key_str not in name_to_id:
            print(f"Error: project_split_overrides key '{key_str}' is not a known project name in label_studio.project_list. Only names are allowed.")
            sys.exit(1)
        if str(split) not in {"train", "test"}:
            print(f"Error: project_split_overrides for '{key_str}' must be either 'train' or 'test', got '{split}'.")
            sys.exit(1)
        overrides_by_id[str(name_to_id[key_str])] = str(split)

    print("\nStarting train-test split...")
    project_image_map_path = os.path.join(final_dir_to_process, 'project_image_map.json')
    train_test_split(final_dir_to_process, desired_ratio=config['train_test_split_ratio'], project_image_map_path=project_image_map_path, project_split_overrides=overrides_by_id)

    # Cropping after the split (train/test) as per original behavior
    if 'cropping' in config and config['cropping']['enabled']:
        print("\nStarting cropping process after split...")
        zone_class_names = config.get('zone_class_names', [])
        zone_class_mapping = {name: str(i) for i, name in enumerate(zone_class_names)}
        perform_cropping(
            base_dir=final_dir_to_process,
            cropping_config_path=config['cropping']['cropping_config_path'],
            zone_class_mapping=zone_class_mapping,
            save_updated_zone_masks=config['cropping'].get('save_updated_zone_masks', False),
            splits=['train', 'test']
        )

    print("\nStarting upload to HuggingFace...")
    upload_to_huggingface_yolo(
        final_dir_to_process, 
        config.get('huggingface', {}), 
        use_mask=config.get('convert_box_to_mask', False),
        clean_up=False, # Keep data for inspection
        class_names=config['spatter_class_names'],
        download=True
    )



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spatter Segmentation Datalake Pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file", type=str)
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['gcp']['credentials_file']
    
    # Create a unique directory for this run to avoid conflicts
    unique_id = str(uuid.uuid4())
    base_run_dir = os.path.join(config['download_dir'], unique_id)
    os.makedirs(base_run_dir, exist_ok=True)
    print(f"Created temporary run directory: {base_run_dir}")
        
    run_pipeline(config, base_run_dir)

    print("Pipeline finished successfully.")
    # The clean_up parameter in upload_to_huggingface_yolo can be used to remove the run directory


