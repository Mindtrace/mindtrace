import os
import argparse
import yaml
import uuid
import numpy as np
import cv2
from PIL import Image
import json
from concurrent.futures import ThreadPoolExecutor
from google.cloud import storage
from PIL import Image
import requests
import sys
import shutil 
from collections import defaultdict
import random
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig
from mtrix.datalake import Datalake

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

def download_data(json_path, images_save_path, masks_save_path, class_names, workers, ignore_holes=True, delete_empty_masks=True):
    os.makedirs(images_save_path, exist_ok=True)
    os.makedirs(masks_save_path, exist_ok=True)
    idx2class = {i: n for i, n in enumerate(class_names)}
    class2idx = {n: i for i, n in enumerate(class_names)}
    with open(json_path, 'r') as f:
        data = json.load(f)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda t: download_image(t, images_save_path), data))

    for d in data:
        image_local_path = os.path.join(images_save_path, d['data']['image'].split('/')[-1])
        image = Image.open(image_local_path)
        w, h = image.size
        mask = np.zeros((h, w), dtype=np.uint8)
        
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
            masks_save_path,
            d['data']['image'].split('/')[-1].replace('.jpg', '_mask.png')
        )
        cv2.imwrite(mask_save_path, mask)

    if delete_empty_masks:
        print("\nPost-processing: Deleting empty masks and corresponding images...")
        deleted_count = 0
        for item in data:
            image_filename = item['data']['image'].split('/')[-1]
            mask_filename = image_filename.replace('.jpg', '_mask.png')
            mask_filepath = os.path.join(masks_save_path, mask_filename)

            if os.path.exists(mask_filepath):
                mask = cv2.imread(mask_filepath, cv2.IMREAD_GRAYSCALE)
                if mask is not None and np.all(mask == 0):
                    print(f"Found empty mask: {mask_filepath}")
                    os.remove(mask_filepath)

                    image_filepath = os.path.join(images_save_path, image_filename)
                    if os.path.exists(image_filepath):
                        print(f"Deleting corresponding image: {image_filepath}")
                        os.remove(image_filepath)
                    
                    deleted_count += 1
        
        print(f"\nPost-processing complete. Deleted {deleted_count} empty masks and their images.")

def train_test_split(masks_save_path, images_save_path, desired_ratio=0.2):
    name2c = {}
    for i in os.listdir(masks_save_path):
        image = cv2.imread(os.path.join(masks_save_path, i))
        name2c[i] = np.unique(image)
    data = name2c

    # --- STEP 1: Build class-to-image map ---
    class_to_images = defaultdict(set)
    for img, classes in data.items():
        for cls in classes:
            class_to_images[int(cls)].add(img)

    # --- STEP 2: Greedily cover all classes in test set ---
    required_classes = set(class_to_images.keys())
    covered_classes = set()
    test_set = set()

    while covered_classes != required_classes:
        best_img = None
        best_new_coverage = set()

        for img, classes in data.items():
            if img in test_set:
                continue
            new_coverage = set(classes) - covered_classes
            if len(new_coverage) > len(best_new_coverage):
                best_img = img
                best_new_coverage = new_coverage

        if best_img is None:
            break
        test_set.add(best_img)
        covered_classes.update(best_new_coverage)

    # --- STEP 3: Enforce ratio-based test set size ---
    all_images = set(data.keys())
    target_test_size = int(len(all_images) * desired_ratio)

    # Fill up the test set randomly (without re-adding existing ones)
    remaining_candidates = list(all_images - test_set)
    random.seed(42)
    random.shuffle(remaining_candidates)

    for img in remaining_candidates:
        if len(test_set) >= target_test_size:
            break
        test_set.add(img)

    # Final split
    train_set = all_images - test_set

    # --- OUTPUT ---
    train_set = sorted(train_set)
    test_set = sorted(test_set)
    
    source_mask = masks_save_path
    target_mask_train = os.path.join(masks_save_path, 'train')
    target_mask_test = os.path.join(masks_save_path, 'test')
    source_image = images_save_path
    target_image_train = os.path.join(images_save_path, 'train')
    target_image_test = os.path.join(images_save_path, 'test')

    os.makedirs(target_image_test, exist_ok=True )
    os.makedirs(target_image_train, exist_ok=True )
    os.makedirs(target_mask_train, exist_ok=True )
    os.makedirs(target_mask_test, exist_ok=True )
    for mask in train_set:
        try:
            shutil.move(os.path.join(source_mask, mask),os.path.join(target_mask_train, mask))
            image_name = mask.replace('_mask.png', '.jpg')
            shutil.move(os.path.join(source_image, image_name), os.path.join(target_image_train, image_name))
        except Exception as e:
            print(e)


    for mask in test_set:
        try: 
            shutil.move(os.path.join(source_mask, mask),os.path.join(target_mask_test, mask))
            image_name = mask.replace('_mask.png', '.jpg')
            shutil.move(os.path.join(source_image, image_name), os.path.join(target_image_test, image_name))
        except Exception as e:
            print(e)

def upload_to_huggingface(download_dir, huggingface_config, class_names, clean_up=True):
    dataset_name = huggingface_config.get('dataset_name')
    version = huggingface_config.get('version')
    existing_dataset = huggingface_config.get('existing_dataset')
    existing_version = huggingface_config.get('existing_version')
    token = huggingface_config.get('token')
    gcp_creds_path = huggingface_config.get('gcp_creds_path')
    
    os.environ['HF_TOKEN'] = token
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_creds_path
    
    datalake = Datalake(
        hf_token = token,    
        gcp_creds_path = gcp_creds_path,
        datalake_dir = download_dir
    )
    ds = datalake.get_dataset(
        dataset_name = existing_dataset,
        version = existing_version
    )

    datalake_train_path = os.path.join(download_dir, existing_dataset, 'splits', 'train')
    datalake_test_path = os.path.join(download_dir, existing_dataset, 'splits', 'test')
    
    for file in os.listdir(os.path.join(datalake_train_path, 'images')):
        image_path = os.path.join(datalake_train_path, 'images', file)
        mask_path = os.path.join(datalake_train_path, 'masks', file.replace('.jpg', '_mask.png'))
        shutil.move(image_path, os.path.join(download_dir, 'images', 'train', file))
        shutil.move(mask_path, os.path.join(download_dir, 'masks', 'train', file.replace('.jpg', '_mask.png')))

    for file in os.listdir(os.path.join(datalake_test_path, 'images')):
        image_path = os.path.join(datalake_test_path, 'images', file)
        mask_path = os.path.join(datalake_test_path, 'masks', file.replace('.jpg', '_mask.png'))
        shutil.move(image_path, os.path.join(download_dir, 'images', 'test', file))
        shutil.move(mask_path, os.path.join(download_dir, 'masks', 'test', file.replace('.jpg', '_mask.png')))
    
    shutil.rmtree(datalake_train_path)
    shutil.rmtree(datalake_test_path)
    shutil.rmtree(os.path.join(download_dir, existing_dataset))
    
    target_path = os.path.join(download_dir, dataset_name)
    source_images_train = os.path.join(download_dir, 'images', 'train')
    source_masks_train  = os.path.join(download_dir, 'masks', 'train')

    source_images_test = os.path.join(download_dir, 'images', 'test')
    source_masks_test  = os.path.join(download_dir, 'masks', 'test')

    os.makedirs(os.path.join(target_path, 'splits' ,'train', 'masks'), exist_ok=True)
    os.makedirs(os.path.join(target_path, 'splits', 'test', 'masks'), exist_ok=True)
    os.makedirs(os.path.join(target_path, 'splits', 'train', 'images'), exist_ok=True)
    os.makedirs(os.path.join(target_path, 'splits', 'test', 'images'), exist_ok=True)
    
    name2c = {}
    for i in os.listdir(source_masks_train):
        image = cv2.imread(os.path.join(source_masks_train, i))
        name2c[i] = np.unique(image)

    train_type = {}
    for k, v in name2c.items():
        if max(v) > 10:
            train_type[k.replace('_mask.png', '.jpg')] = 'OB'
        else: 
            train_type[k.replace('_mask.png', '.jpg')] = 'IB'

    name2c = {}
    for i in os.listdir(source_masks_test):
        image = cv2.imread(os.path.join(source_masks_test, i))
        name2c[i] = np.unique(image)


    test_type = {}
    for k, v in name2c.items():
        if max(v) > 10:
            test_type[k.replace('_mask.png', '.jpg')] = 'OB'
        else: 
            test_type[k.replace('_mask.png', '.jpg')] = 'IB'


    train_annotations = {}
    train_metadata = {}
    train_data_files = {}


    val_annotations = {}
    val_metadata = {}
    val_data_files = {}


    for i in os.listdir(source_images_train):
        train_annotations[i] = {
            'file_name' : i, 
            'masks' : i.replace('.jpg', '_mask.png'),
            'PartType' : train_type[i],
            'CameraIDX' : -1
        }
        train_data_files[i] = os.path.join(source_images_train, i)
        shutil.copy(os.path.join(source_images_train, i), os.path.join(target_path, 'splits', 'train', 'images', i))
        train_data_files[i.replace('.jpg', '_mask.png')] = os.path.join(target_path, 'splits', 'train', 'masks', i.replace('.jpg', '_mask.png'))
        shutil.copy(os.path.join(source_masks_train, i.replace('.jpg', '_mask.png')), os.path.join(target_path, 'splits', 'train', 'masks', i.replace('.jpg', '_mask.png')))
        
        train_metadata[i] = {"file_name": i, "metadata" : {'CameraIDX' : 'M', 
                                                        'PartType': train_type[i]}
                                }                   

    for i in os.listdir(source_images_test):
        val_annotations[i] = {
            'file_name' : i, 
            'masks' : i.replace('.jpg', '_mask.png'),
            'PartType' : test_type[i],
            'CameraIDX' : -1
        }
        val_data_files[i] = os.path.join(source_images_test, i)
        shutil.copy(os.path.join(source_images_test, i), os.path.join(target_path,'splits',  'test', 'images', i))
        val_data_files[i.replace('.jpg', '_mask.png')] = os.path.join(target_path, 'splits', 'test', 'masks', i.replace('.jpg', '_mask.png'))
        shutil.copy(os.path.join(source_masks_test, i.replace('.jpg', '_mask.png')), os.path.join(target_path, 'splits', 'test', 'masks', i.replace('.jpg', '_mask.png')))

        val_metadata[i] = {"file_name": i, "metadata" : {'CameraIDX' : 'M', 
                                                        'PartType': test_type[i]}}


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
                "name" : 'PartType',
                "type" : 'classification',
                "classes" : ['IB', 'OB'],
                "required" : False
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
    datalake.update_dataset(
        src = os.path.join(download_dir, dataset_name),
        dataset_name = dataset_name,
        version = version,
    )
    datalake.publish_dataset(
        dataset_name = dataset_name,
        version = version,
    )

    if clean_up:
        shutil.rmtree(download_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete Label Studio Pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file", type=str)
    parser.add_argument("--job_id", type=str, default=None, help="Custom job ID")
    parser.add_argument("--delay", type=int, default=30, help="Delay in seconds before syncing storage (default: 30)")
    
    args = parser.parse_args()
    
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['gcp']['credentials_file']
    
    class_names = config['class_names']
    workers = config['workers']
    download_dir = config['download_dir']
    unique_id = str(uuid.uuid4())
    unique_id = '76e11055-4af8-4e95-b682-2c26cbcb6bbe'
    download_dir = os.path.join(download_dir, unique_id)
    label_studio_config = config['label_studio']
    api_config = label_studio_config['api']
    project_list = label_studio_config['project_list']
    export_type = label_studio_config['export_type']
    
    
    label_studio = LabelStudio(
            LabelStudioConfig(
                url=api_config['url'],
                api_key=api_config['api_key'],
                gcp_creds=api_config['gcp_credentials_path']
            )
        )

    project_ids = []
    
    for project in project_list:
        project_ids.append(label_studio.get_project_by_name(project))
    
    
    for project in project_ids:
        export_path = os.path.join(download_dir, str(project.id) +'.json')
        print('Exporting project', project.id, 'to', export_path)
        label_studio.export_annotations(
            project_id=project.id,
            export_type=export_type,
            export_location=export_path
        )
        
        images_save_path = os.path.join(download_dir, 'images')
        masks_save_path = os.path.join(download_dir, 'masks')
        
        download_data(
            export_path, 
            images_save_path, 
            masks_save_path, 
            class_names, 
            workers, 
            ignore_holes=config['ignore_holes'], 
            delete_empty_masks=config['delete_empty_masks']
        )
        
        train_test_split(masks_save_path, images_save_path, desired_ratio=config['train_test_split_ratio'])
        
        upload_to_huggingface(download_dir, config.get('huggingface', {}), class_names, clean_up=True)
        
        
        
        
        
            
            