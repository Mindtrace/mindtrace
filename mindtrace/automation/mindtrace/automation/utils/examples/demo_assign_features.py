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
    mapping = {"c1": "cam1", "c2": "cam2"}

    # boxes_by_image: list per image; each item is a NumPy array shaped (N,4)
    boxes_by_image = [
        np.asarray([
            [112, 55, 125, 65],          # weld W1
            [150, 55, 165, 65],          # weld W2
            [205, 55, 225, 75],          # hole H1 → present
        ]),
        np.asarray([]).reshape(0, 4)  # c2: missing W3
    ]

    results = det.detect(inputs=boxes_by_image, image_keys=image_keys, mapping=mapping)
    print_json("BOXES RESULT", results)


def run_masks():
    det = FeatureDetector(CONFIG_PATH)
    image_keys = ["c1", "c2"]
    mapping = {"c1": "cam1", "c2": "cam2"}
    class_id = 1  # mask class used when feature.params.class_id is not set

    mask1 = np.zeros((200, 300), dtype=np.uint8)
    # WL11_13 weld group: two separate contours inside the same ROI (expect 2)
    cv2.rectangle(mask1, (112, 55), (125, 65), color=1, thickness=-1)
    cv2.rectangle(mask1, (150, 55), (165, 65), color=1, thickness=-1)
    # H1 hole present
    cv2.rectangle(mask1, (205, 55), (225, 75), color=2, thickness=-1)

    mask2 = np.zeros((200, 300), dtype=np.uint8)  # W2 missing

    results = det.detect(inputs=[mask1, mask2], image_keys=image_keys, mapping=mapping, class_id=class_id)
    print_json("MASKS RESULT", results)


if __name__ == "__main__":
    run_boxes()
    run_masks()


