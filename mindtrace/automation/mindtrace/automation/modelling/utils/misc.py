import os
import uuid
import glob
import json
import logging
from datetime import datetime, timezone
from ultralytics import YOLO, RTDETR, YOLOv10
import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
from mindtrace.automation.modelling.utils.letterbox import LetterBox
import torch
import numpy as np
from torch.serialization import add_safe_globals
from ultralytics.nn.tasks import YOLOv10DetectionModel

# Add the custom model class to safe globals
add_safe_globals([YOLOv10DetectionModel])
from ultralytics import YOLO, RTDETR, YOLOv10

def resize_img(img, key, img_size, letterbox=None):
	"""
	Resizes an image and converts it to RGB format.

	Args:
		img (numpy.ndarray): The input image to be resized.
		key(str): Camera id for the image.
		img_size (int): The target size to resize the image to.
		letterbox (callable, optional): A function for letterbox resizing. If None, a standard resize is applied.

	Returns:
		tuple: A tuple containing:
			- img (numpy.ndarray): The original image.
			- key(str): The camera id for the image.
			- img_resize (numpy.ndarray): The resized image in RGB format.
			- img.shape[:2] (tuple): The original image dimensions.
			- transformations (tuple): The transformation details applied (ratio, dw, dh).
	"""
	if letterbox:
		img_resize = cv2.cvtColor(letterbox(img), cv2.COLOR_BGR2RGB)
		transformations = (letterbox.ratio, letterbox.dw, letterbox.dh)
	else:
		img_resize = cv2.cvtColor(cv2.resize(img, (img_size, img_size)), cv2.COLOR_BGR2RGB)
		transformations = ((1, 1), 0, 0)
	return img, key, img_resize, img.shape[:2], transformations

def resize_imgs(imgs, keys, img_size, use_letterbox=True):
	"""
	Resizes a list of images using multithreading and converts them to RGB format.
	Since the resize is done in parallel, the original data is also returned to keep same order
	Args:
		imgs (list of numpy.ndarray): The list of input images to be resized.
		keys (list of str): A list of camera ids.
		img_size (int): The target size to resize the images to.
		use_letterbox (bool, optional): Whether to use letterbox resizing. Defaults to True.

	Returns:
		tuple: A tuple containing:
			- og_images (list of numpy.ndarray): The original images in new order.
			- og_keys (list of str): The list of camera ids in new order.
			- resized_imgs (list of numpy.ndarray): The resized images in RGB format in new order.
			- img_sizes (list of tuple): The original image dimensions.
			- transformations (list of tuple): The transformation details applied (ratio, dw, dh).
	"""
	# if use_letterbox:
	# 	letterbox = LetterBox((img_size, img_size), auto=False, stride=32)
	# else:
	# 	letterbox = None

	with ThreadPoolExecutor() as executor:
		if use_letterbox:
			futures = [executor.submit(resize_img, img, key, img_size, LetterBox((img_size, img_size), auto=False, stride=32)) for img, key in zip(imgs, keys)]
		else:
			futures = [executor.submit(resize_img, img, key, img_size, None) for img, key in zip(imgs, keys)]
		img_sizes = []
		og_images = []
		og_keys = []
		resized_imgs = []
		transformations = []

		for future in as_completed(futures):
			img, key, img_resize, size, transformation = future.result()

			img_sizes.append(size)
			og_images.append(img)
			og_keys.append(key)
			resized_imgs.append(img_resize)
			transformations.append(transformation)

	return og_images, og_keys, resized_imgs, img_sizes, transformations


def obj_results_to_boxes(obj_results, img_sizes):
	"""
	Converts object detection results to bounding box format.

	Args:
	obj_results (list): List of object detection results.

	Returns:
	list: A list of bounding boxes in format (xc, yc, w, h, conf, cls_id, cls_name)..
	"""
	results = []
	for obj_result in obj_results:
		boxes = [
	  		[
				int((box[0] + box[2]) // 2),
				int((box[1] + box[3]) // 2),
				int(box[2] - box[0]),
				int(box[3] - box[1]),
				box[4],
				box[5],
				obj_result.names[int(box[5])]
			]
			for box in obj_result.boxes.data.cpu().numpy()
  		]
		results.append(boxes)
	return results



def obj_results_to_boxes_letterbox(obj_results, transformations=None):
	"""
	Converts object detection results to bounding box format when using letterbox.
	Scales boxes back to original image size without padding

	Args:
	obj_results (list): List of object detection results in format (xc, yc, w, h, conf, cls_id, cls_name).

	Returns:
	list: A list of bounding boxes.
	"""
	results = []
	if transformations is None:
		transformations = [[[1, 1], 0, 0] for i in range(len(obj_results))]

	# Unpad results
	for j, [obj_result, (ratio, dw, dh)] in enumerate(zip(obj_results, transformations)):
		boxes = []
		for box in obj_result.boxes.data.cpu().numpy():
			x1, y1, x2, y2, conf, cls_id = box
			cls_name = obj_result.names[int(box[5])]
			x1 = (x1 - dw) / ratio[0]
			y1 = (y1 - dh) / ratio[1]
			x2 = (x2 - dw) / ratio[0]
			y2 = (y2 - dh) / ratio[1]
			xc, yc = (x1 + x2) // 2, (y1 + y2) // 2
			w, h = (x2 - x1), (y2 - y1)
			boxes.append([int(xc), int(yc), int(w), int(h), conf, cls_id, cls_name])

		results.append(boxes)
	return results



def load_weld_detector (detector_file, model_path, metdata_name='metadata.json'):
    """
    Load the MIG detector from a file.

    Args:
        detector_file (str): Path to the detector file.
        model_path (str): Path to the model directory.

    Returns:
        MigClassifier: Loaded MIG classifier.
    """

    with open(os.path.join(model_path, metdata_name), 'r') as json_file:
            metadata = json.load(json_file)


    if 'yolo' in metadata['model_type'].lower():
        # Check for 'v10' in the model type to load YOLOv10
        if 'v10' in metadata['model_type'].lower():
            print("$$$$")
            print(detector_file)
            return YOLOv10(model=detector_file)
        else:
            # Load default YOLO model for other YOLO types
            return YOLO(model=detector_file)
    elif 'rt_detr' in metadata['model_type'].lower():
        # Load RT-DETR model
        return RTDETR(model=detector_file)
    else:
        # Raise an error if the model type is not supported
        raise ValueError(f"Model type {metadata['model_type']} not supported.")


def list_files_with_extensions(directory, extensions):
    """
    List files in a directory with specified extensions.

    Args:
        directory (str): Directory path.
        extensions (list): List of extensions (e.g., ['.pt', '.ckpt']).

    Returns:
        list: List of filenames with specified extensions.
    """
    # Create a pattern to match files with specified extensions
    pattern = os.path.join(directory, '*')
    files = []

    for ext in extensions:
        files.extend(glob.glob(pattern + ext))

    return files


def weld_detection(imgs, model, imgsz = 640, conf = 0.5, iou=0.7, use_letterbox=True, device='cuda', keys=['input_image']):
    """
    Detects welds in a list of images using a specified model.
    Original imgs and keys are returned since threadpool is used for resize

    Args:
        imgs (list of numpy.ndarray): The list of input images for weld detection.
        keys (list of string): A list of camera ids.
        model (torch.nn.Module): The model used for detection.
        imgsz (int): The target size to resize the images to.
        conf (float): Confidence threshold for detection.
        iou (float): Intersection over Union (IoU) threshold for detection.
        use_letterbox (bool, optional): Whether to use letterbox resizing. Defaults to True.

    Returns:
        tuple: A tuple containing:
            - og_images (list of numpy.ndarray): The original images in new order.
            - og_keys (list of string): The camera ids for the images in new order.
            - boxes (list): The detected bounding boxes for each image in format [(xcyc, y1, w, h, conf, cls_id, cls_name)]
    """

    og_images, og_keys, resized_imgs, img_sizes, transformations = resize_imgs(imgs, keys, imgsz, use_letterbox=use_letterbox)

    tensor_imgs = torch.from_numpy(np.array(resized_imgs)/255).to(device).permute(0,3,1,2)
    with torch.no_grad():
        results = model(
                    tensor_imgs,
                    save=False,
                    imgsz=(imgsz, imgsz),
                    conf=conf,
                    iou=iou,
                    verbose=False,
                    half=False,
                )
    if use_letterbox:
        boxes = obj_results_to_boxes_letterbox(results, transformations=transformations)
    else:
        boxes = obj_results_to_boxes(results, img_sizes=img_sizes)
    return og_images, og_keys, boxes