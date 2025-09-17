import json
import os
import cv2
import numpy as np

from mindtrace.automation.utils.feature_detector import FeatureDetector


HERE = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(HERE, "config_demo.json")


def print_json(title, obj):
    print(title)
    print(json.dumps(obj, indent=2))


def run_boxes():
    det = FeatureDetector(CONFIG_PATH)
    image_keys = ["c1", "c2"]
    mapping = {"c1": "Basler:laser_cam1", "c2": "Basler:laser_cam2"}

    # boxes_by_image: list per image; each box is [x1,y1,x2,y2] or dict with bbox/x1..y2
    boxes_by_image = [
        [
            [110, 55, 170, 65],          # weld W1 (length 60 px ≥ 50 px) → present
            {"bbox": [205, 55, 225, 75]} # hole H1 → present
        ],
        []  # c2: missing W2
    ]

    results = det.detect(inputs=boxes_by_image, image_keys=image_keys, mapping=mapping)
    print_json("BOXES RESULT", results)


def run_masks():
    det = FeatureDetector(CONFIG_PATH)
    image_keys = ["c1", "c2"]
    mapping = {"c1": "Basler:laser_cam1", "c2": "Basler:laser_cam2"}
    weld_class_id = 1  # default class for welds

    mask1 = np.zeros((200, 300), dtype=np.uint8)
    # W1 weld (short): length 35 px (< 50 px threshold)
    cv2.rectangle(mask1, (110, 55), (145, 65), color=1, thickness=-1)
    # H1 hole present
    cv2.rectangle(mask1, (205, 55), (225, 75), color=2, thickness=-1)

    mask2 = np.zeros((200, 300), dtype=np.uint8)  # W2 missing

    results = det.detect(inputs=[mask1, mask2], image_keys=image_keys, mapping=mapping, weld_class_id=weld_class_id)
    print_json("MASKS RESULT", results)


if __name__ == "__main__":
    run_boxes()
    run_masks()


