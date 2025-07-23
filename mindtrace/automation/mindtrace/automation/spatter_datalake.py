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
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig
from mtrix.datalake import Datalake

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

def download_data_yolo(
    json_path, 
    images_save_path, 
    labels_save_path, 
    zone_masks_save_path,
    workers, 
    zone_class_names,
    ignore_holes=True,
    delete_empty_masks=True
):
    os.makedirs(images_save_path, exist_ok=True)
    os.makedirs(labels_save_path, exist_ok=True)
    os.makedirs(zone_masks_save_path, exist_ok=True)
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

    for d in data:
        image_local_path = os.path.join(images_save_path, d['data']['image'].split('/')[-1])
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

    for task in data:
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
            
        img = Image.open(image_path)
        img_width, img_height = img.size

        labels = []
        for a in task.get('annotations', []):
            for r in a.get('result', []):
                if 'value' in r and 'rectanglelabels' in r['value']:
                    if 'Spatter' in r['value']['rectanglelabels']:
                        labels.append(r['value'])

        if not labels:
            with open(label_path, 'w') as f:
                f.write('')
            continue

        conv = labelstudio_to_yolo(labels, img_width, img_height)
        l = ''
        for c in conv:
            l = l + '0 ' + str(c[0]) + ' ' + str(c[1]) + ' ' + str(c[2]) + ' ' + str(c[3]) + '\n'
        with open(label_path, 'w') as f:
            f.write(l)

def generate_masks_from_boxes(images_dir, labels_dir, masks_save_path, device_id='cuda:0'):
    if not SAM_AVAILABLE:
        print("torch or mtrix.models.SegmentAnything not found. Cannot generate masks.")
        sys.exit(1)
        
    device = torch.device(device_id)
    model = SegmentAnything(model='vit_h', device=device)

    os.makedirs(masks_save_path, exist_ok=True)

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
            continue

        model.set_image(np.array(image))
        
        all_masks = []
        for b in boxes_xyxy:
            masks, _, _ = model.predict(box=np.array(b), multimask_output=False)
            all_masks.append(masks[0])

        combined_mask = np.any(np.stack(all_masks, axis=0), axis=0).astype(np.uint8)
        mask_image = Image.fromarray(combined_mask * 255, mode='L')
        mask_image.save(os.path.join(masks_save_path, name.rsplit('.', 1)[0] + '_mask.png'), mode='L')
    print("Mask generation complete.")

def train_test_split(base_dir, desired_ratio=0.2):
    images_dir = os.path.join(base_dir, 'images')
    
    all_images = [f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    random.seed(42)
    random.shuffle(all_images)
    
    test_size = int(len(all_images) * desired_ratio)
    test_set = set(all_images[:test_size])
    train_set = set(all_images[test_size:])

    for split_name, image_set in [('train', train_set), ('test', test_set)]:
        for f in image_set:
            # Move image
            source_image_path = os.path.join(images_dir, f)
            target_image_dir = os.path.join(images_dir, split_name)
            os.makedirs(target_image_dir, exist_ok=True)
            shutil.move(source_image_path, os.path.join(target_image_dir, f))

            # Move label
            labels_dir = os.path.join(base_dir, 'labels')
            label_filename = f.rsplit('.', 1)[0] + '.txt'
            source_label_path = os.path.join(labels_dir, label_filename)
            if os.path.exists(source_label_path):
                target_label_dir = os.path.join(labels_dir, split_name)
                os.makedirs(target_label_dir, exist_ok=True)
                shutil.move(source_label_path, os.path.join(target_label_dir, label_filename))
            
            # Move mask
            masks_dir = os.path.join(base_dir, 'masks')
            mask_filename = f.rsplit('.', 1)[0] + '_mask.png'
            source_mask_path = os.path.join(masks_dir, mask_filename)
            if os.path.exists(source_mask_path):
                target_mask_dir = os.path.join(masks_dir, split_name)
                os.makedirs(target_mask_dir, exist_ok=True)
                shutil.move(source_mask_path, os.path.join(target_mask_dir, mask_filename))

    print("Train-test split complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spatter Segmentation Datalake Pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file", type=str)
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    convert_box_to_mask = config.get('convert_box_to_mask', False)

    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['gcp']['credentials_file']
    
    download_dir = config['download_dir']
    unique_id = str(uuid.uuid4())
    unique_id = "test"
    download_dir = os.path.join(download_dir, unique_id)
    os.makedirs(download_dir, exist_ok=True)
        
    label_studio_config = config['label_studio']
    api_config = label_studio_config['api']
    
    label_studio = LabelStudio(
        LabelStudioConfig(
            url=api_config['url'],
            api_key=api_config['api_key'],
            gcp_creds=api_config['gcp_credentials_path']
        )
    )

    project_ids = [label_studio.get_project_by_name(p) for p in label_studio_config['project_list']]
    
    images_save_path = os.path.join(download_dir, 'images')
    labels_save_path = os.path.join(download_dir, 'labels')
    os.makedirs(images_save_path, exist_ok=True)
    os.makedirs(labels_save_path, exist_ok=True)

    for project in project_ids:
        export_path = os.path.join(download_dir, f"{project.id}.json")
        print(f"Exporting project {project.id} to {export_path}")
        label_studio.export_annotations(
            project_id=project.id,
            export_type=label_studio_config['export_type'],
            export_location=export_path
        )
        
        zone_masks_save_path = os.path.join(download_dir, 'zone_masks')
        download_data_yolo(
            export_path, 
            images_save_path, 
            labels_save_path, 
            zone_masks_save_path,
            config['workers'], 
            config['zone_class_names'],
            ignore_holes=config['ignore_holes'],
            delete_empty_masks=config['delete_empty_masks'])
    
    if convert_box_to_mask:
        masks_save_path = os.path.join(download_dir, 'masks')
        generate_masks_from_boxes(images_save_path, labels_save_path, masks_save_path)

