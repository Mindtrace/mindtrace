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
from tqdm import tqdm
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
            # print(f"[SUCCESS] {url} → {fname}")
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
            # print(f"[SUCCESS] {url}")
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

def download_and_process_image(args):
    d, images_save_path, masks_save_path, class2idx, ignore_holes, remove_holes, fill_holes, kernel_size, num_iterations, enlarge_zones_map = args
    idx2class = {i: n for i, n in enumerate(class2idx)}
    fname = download_image(d, images_save_path)
    camera_name = fname.split('-')[0]
    # Prepare a proper uint8 morphological kernel for dilation
    kernel_size = int(kernel_size)
    if isinstance(kernel_size, int):
        k = int(kernel_size)
        if k <= 0:
            k = 1
        if k % 2 == 0:
            k += 1
        dilation_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    elif isinstance(kernel_size, (tuple, list)) and len(kernel_size) == 2:
        kx, ky = int(kernel_size[0]), int(kernel_size[1])
        kx = max(1, kx | 1)
        ky = max(1, ky | 1)
        dilation_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kx, ky))
    else:
        dilation_kernel = np.ones((3, 3), dtype=np.uint8)
    if fname.startswith("["):  # Error or skipped
        print(f"Skipping processing for {d['data']['image']} due to download issue: {fname}")
        return None

    image_local_path = os.path.join(images_save_path, fname)
    try:
        image = Image.open(image_local_path)
    except Exception as e:
        print(f"Failed to open image {image_local_path}: {e}")
        return None

    w, h = image.size
    mask = np.zeros((h, w), dtype=np.uint8)

    all_hole_polygons = []
    all_normal_polygons = []
    for an in d['annotations']:
        hole_polygons = []
        normal_polygons = []
        
        for result in an['result']:
            if result['type'] != 'polygonlabels':
                continue

            class_name = result['value']['polygonlabels'][0]
            if class_name not in class2idx:
                continue

            points = (np.array(result['value']['points']) * np.array([w, h]) / 100).astype(np.int32)
            points = points.reshape((-1, 1, 2))

            if class_name == 'Hole':
                hole_polygons.append(points)
            else:
                normal_polygons.append((points, class2idx[class_name]))
        
        all_hole_polygons.extend(hole_polygons)
        all_normal_polygons.extend(normal_polygons)

    all_normal_polygons.sort(key=lambda p: p[1])

    for contour, class_id in all_normal_polygons:
        if fill_holes:
            cv2.drawContours(mask, [contour], -1, color=class_id, thickness=cv2.FILLED)
        else:
            cv2.fillPoly(mask, [contour], color=class_id)
        if enlarge_zones_map:
            class_name = idx2class[class_id]
            if camera_name in enlarge_zones_map:
                print(camera_name)
                print(enlarge_zones_map)
                print(camera_name in enlarge_zones_map, class_name, class_name in enlarge_zones_map[camera_name])
                if class_name in enlarge_zones_map[camera_name]:
                    print(f"Enlarging {class_name} for {camera_name}")
                    mask = cv2.dilate(mask, dilation_kernel, iterations=int(num_iterations))

    if not ignore_holes and 'Hole' in class2idx:
        for contour in all_hole_polygons:
            cv2.fillPoly(mask, [contour], color=class2idx['Hole'])
    if remove_holes and 'background' in class2idx:
        for contour in all_hole_polygons:
            cv2.fillPoly(mask, [contour], color=class2idx['background'])

    mask_fname = os.path.splitext(fname)[0] + '_mask.png'
    mask_save_path = os.path.join(masks_save_path, mask_fname)
    cv2.imwrite(mask_save_path, mask)
    
    has_holes = len(all_hole_polygons) > 0
    return d, fname, has_holes


def download_data(
    json_path, 
    images_save_path, 
    masks_save_path, 
    class_names, 
    workers, 
    ignore_holes=True, 
    remove_holes=True, 
    delete_empty_masks=True,
    hole_id=1,
    fill_holes=False,
    kernel_size=21,
    num_iterations=3,
    enlarge_zones_map=None):
    os.makedirs(images_save_path, exist_ok=True)
    os.makedirs(masks_save_path, exist_ok=True)
    idx2class = {i: n for i, n in enumerate(class_names)}
    class2idx = {n: i for i, n in enumerate(class_names)}
    with open(json_path, 'r') as f:
        data = json.load(f)

    tasks = [(d, images_save_path, masks_save_path, class2idx, ignore_holes, remove_holes, fill_holes, kernel_size, num_iterations, enlarge_zones_map) for d in data]
    
    processed_items = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        with tqdm(total=len(tasks), desc="Downloading and Processing Images") as pbar:
            results = executor.map(download_and_process_image, tasks)
            for item in results:
                if item is not None:
                    processed_items.append(item)
                pbar.update(1)

    no_hole_items = []
    for item, fname, has_holes in processed_items:
        if not has_holes:
            no_hole_items.append(item)

    if delete_empty_masks:
        print("\nPost-processing: Deleting empty masks and corresponding images...")
        deleted_count = 0
        for item, fname, has_holes in processed_items:
            mask_filename = os.path.splitext(fname)[0] + '_mask.png'
            mask_filepath = os.path.join(masks_save_path, mask_filename)

            if os.path.exists(mask_filepath):
                mask = cv2.imread(mask_filepath, cv2.IMREAD_GRAYSCALE)
                if mask is not None and np.all(mask == 0):
                    print(f"Found empty mask: {mask_filepath}")
                    os.remove(mask_filepath)

                    image_filepath = os.path.join(images_save_path, fname)
                    if os.path.exists(image_filepath):
                        print(f"Deleting corresponding image: {image_filepath}")
                        os.remove(image_filepath)
                    
                    deleted_count += 1
        
        print(f"\nPost-processing complete. Deleted {deleted_count} empty masks and their images.")

    return no_hole_items

def train_test_split(masks_save_path, images_save_path, desired_ratio=0.2):
    name2c = {}
    all_masks = [f for f in os.listdir(masks_save_path) if os.path.isfile(os.path.join(masks_save_path, f))]
    for i in all_masks:
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

def upload_to_huggingface(download_dir, huggingface_config, class_names, clean_up=True, remove_holes=True, hole_id=1):
    dataset_name = huggingface_config.get('dataset_name')
    version = huggingface_config.get('version')
    existing_dataset = huggingface_config.get('existing_dataset')
    existing_version = huggingface_config.get('existing_version')
    token = huggingface_config.get('token')
    gcp_creds_path = huggingface_config.get('gcp_creds_path')
    
    os.environ['HF_TOKEN'] = token
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_creds_path
    
    if existing_dataset is not None:
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
            if remove_holes:
                mask = cv2.imread(mask_path)
                mask[mask == hole_id] = 0
                cv2.imwrite(mask_path, mask)
            

            shutil.move(image_path, os.path.join(download_dir, 'images', 'train', file))
            shutil.move(mask_path, os.path.join(download_dir, 'masks', 'train', file.replace('.jpg', '_mask.png')))

        for file in os.listdir(os.path.join(datalake_test_path, 'images')):
            image_path = os.path.join(datalake_test_path, 'images', file)
            mask_path = os.path.join(datalake_test_path, 'masks', file.replace('.jpg', '_mask.png'))
            if remove_holes:
                mask = cv2.imread(mask_path)
                mask[mask == hole_id] = 0
                cv2.imwrite(mask_path, mask)

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
        "incremental": False,  # What does incremental even mean ? 
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
    remove_holes = config['remove_holes']
    hole_id = config['hole_id']
    unique_id = str(uuid.uuid4())
    # unique_id = "21c5aaba-1e4a-4f06-a453-ab1c27391db2"
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
        
        no_hole_items = download_data(
            export_path, 
            images_save_path, 
            masks_save_path, 
            class_names, 
            workers, 
            ignore_holes=config['ignore_holes'], 
            remove_holes=config['remove_holes'],
            delete_empty_masks=config['delete_empty_masks'],
            fill_holes=config['fill_holes'],
            kernel_size=config['enlarge_kernel_size'],
            num_iterations=config['enlarge_iterations'],
            enlarge_zones_map=config['enlarge_zones_map']
        )
        
        if no_hole_items:
            print("\n--- Images without Holes ---")
            for item in no_hole_items:
                print(f"  - Project: {project.title}, Image: {item['data']['image']}")
            print("--------------------------\n")
            
    train_test_split(masks_save_path, images_save_path, desired_ratio=config['train_test_split_ratio'])
        
    upload_to_huggingface(download_dir, config.get('huggingface', {}), class_names, clean_up=True, remove_holes=remove_holes, hole_id=hole_id)
        
        
        
        
        
            
            