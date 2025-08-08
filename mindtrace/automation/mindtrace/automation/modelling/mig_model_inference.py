import os
import json
import torch
import numpy as np
from typing import Optional, Dict, Any, Tuple, List, Union
from enum import Enum
from PIL import Image
import cv2
import shutil
import argparse
import yaml
from mtrix.models.wrappers import HFVisionModelWrapper
from mindtrace.automation.modelling.utils import logits_to_mask
from mindtrace.automation.modelling.utils.mig_classifier import MigClassifier
from mindtrace.automation.modelling.utils.misc import list_files_with_extensions, load_weld_detector, weld_detection, crop_boxes


class ExportType(Enum):
    """Export format types for inference results."""
    BOUNDING_BOX = "bounding_box"
    MASK = "mask"


class ModelInference:
    """Individual model inference class for a specific task."""

    def __init__(
        self,
        config,
        job_id,
        model_path: str,
        task_type: str,  # this is common ml tasks
        model_name: str,
        device: str = "cpu",
        inference_task: Optional[str] = None # this is something pipeline specific like weld detection etc
    ):
        """Initialize model inference.

        Args:
            model_path: Path to the model directory
            task_type: Type of task (object_detection, semantic_segmentation, etc.)
            model_name: Name of the model
            device: Device to run inference on
        """
        self.model_path = model_path
        self.task_type = task_type
        self.model_name = model_name
        self.device = device
        self.model = None
        self.id2label = {}
        self.img_size = None
        self.inference_task = inference_task
        self.job_id = job_id
        self.config = config
        # Load model metadata
        self._load_metadata()
        self._load_id2label()
        self._instantiate_model()

    def _load_metadata(self):
        """Load model metadata from metadata.json."""
        metadata_path = os.path.join(self.model_path, "metadata.json")
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            self.img_size = metadata.get('img_size', [1024, 1024])
            print(f"Loaded metadata for {self.model_name}: task={self.task_type}, img_size={self.img_size}")
        except Exception as e:
            print(f"Error loading metadata: {e}")
            self.img_size = [1024, 1024]

    def _load_id2label(self):
        """Load class mapping from id2label.json."""
        id2label_path = os.path.join(self.model_path, "id2label.json")
        try:
            with open(id2label_path, 'r') as f:
                self.id2label = json.load(f)

            self.label2id = {v: k for k, v in self.id2label.items()}
            print(f"Loaded {len(self.id2label)} class labels")
        except Exception as e:
            print(f"Error loading id2label: {e}")
            self.id2label = {}

    def _instantiate_model(self,):
        """Instantiate the model using HFVisionModelWrapper."""
        try:
            print(f"Instantiating model: {self.model_name} for task: {self.task_type}")
            print(f"Model path: {self.model_path}")

            if self.inference_task == "weld_classification":

                files = list_files_with_extensions(self.model_path, ['.pt', '.ckpt'])


                detector_files = [file for file in files if 'detector' in file]

                weld_detector = load_weld_detector(detector_files[0], self.model_path)

                weld_detector.to(self.device)
                self.model = weld_detector

            else:

                classifier_list = list_files_with_extensions(self.model_path, [".pt"])
                model_pt = torch.load(classifier_list[0], map_location=self.device)
                model = MigClassifier(**model_pt['config'])
                model.load_state_dict(model_pt['state_dict'])
                model = model.eval()
                model = model.to(self.device)
                self.model = model

                print("******")
                print("defect classification LOADED")


            print(f"Model instantiated successfully")
        except Exception as e:
            print(f"Error instantiating model: {e}")
            self.model = None

    def run_inference(
        self,
        image: Union[str, Image.Image, np.ndarray],
        export_type: ExportType = ExportType.BOUNDING_BOX,
        threshold: float = 0.5,
        background_class: int = 0
    ) -> Dict[str, Any]:
        """Run inference on the image.

        Args:
            image: Input image (path, PIL Image, or numpy array)
            export_type: Export format (bounding_box or mask)
            threshold: Confidence threshold for detections
			background_class: Background class for semantic segmentation
        Returns:
            Dictionary with inference results
        """
        if self.model is None:
            raise ValueError("Model not initialized")

        # # Convert image to PIL if needed
        # if isinstance(image, str):
        #     image = Image.open(image).convert('RGB')
        # elif isinstance(image, np.ndarray):
        #     image = Image.fromarray(image).convert('RGB')

        # Run task-specific inference
        if self.task_type == "object_detection":
            result = self._run_object_detection(image, threshold)
        elif self.task_type in ["semantic_segmentation", "universal_segmentation"]:
            result = self._run_semantic_segmentation(image, threshold, background_class)
        else:
            raise ValueError(f"Unsupported task type: {self.task_type}")

        # Convert to requested export format
        # if export_type == ExportType.BOUNDING_BOX and result.get('mask') is not None:
        #     result = self._mask_to_bounding_box(result)
        # elif export_type == ExportType.MASK and result.get('boxes') is not None:
        #     result = self._bounding_box_to_mask(result)

        return result

    def _run_object_detection(self, image: str, threshold: float) -> Dict[str, Any]:
        """Run object detection inference."""
        try:

            if self.inference_task == "weld_classification":
                print(f"Running object detection with threshold {threshold} for {self.inference_task}")

                if self.model is None:
                    raise ValueError("Model not initialized")

                img = Image.open(image)
                image = np.array(img)

                imgs, keys, weld_boxes_list = weld_detection(imgs=  [image], model = self.model)

                return {
                        "boxes": weld_boxes_list,
                        'task_type': 'object_detection'
                    }

            if self.inference_task == "defect_classification":

                boxes_folder = os.path.join(self.config["output_folder"], str(self.job_id), "boxes", "weld_classification")
                box_path = os.path.join(  boxes_folder, os.path.splitext(os.path.basename(image))[0] + ".txt")

                boxes = []


                from pathlib import Path
                with open(Path(box_path), 'r') as f:

                    for line_num, line in enumerate(f, start=1):
                        parts = line.strip().split()

                        # Skip empty or malformed lines
                        if len(parts) == 7:


                            cls_id, cls_name, xc, yc, w, h, conf = map(str, parts)  # or map(str, parts) or map(int, parts)
                            boxes.append((float(xc), float(yc), float(w), float(h), float(conf), cls_id, cls_name))



                img = Image.open(image)
                image = np.array(img)

                crops = crop_boxes(image, boxes)

                classifications_list = []
                severitys_list = []


                if len(crops) > 0:


                    try:
                        # Convert crops to PIL Images if the model expects that format
                        pil_crops = [Image.fromarray(crop) for crop in crops]
                        # Assuming classifier predict_batch exists and takes PIL images
                        # Adapt this call based on the actual classifier interface
                        # The `cond` parameter seems specific, adjust as needed
                        classifications_preds = self.model.predict_batch(
                            pil_crops, cond=[22 for _ in range(len(pil_crops))] # Example cond
                        )

                        classifications = classifications_preds.get('multiclass_preds', [])
                        classifications_list.extend(classifications)




                        # Check for severity predictions
                        if 'severity_preds' in classifications_preds:
                            severitys = classifications_preds['severity_preds']
                            severitys_list.extend(severitys)
                        else:
                            # Provide default 'N/A' if severity is not predicted
                            severitys_list.extend(["N/A"] * len(classifications))

                    except AttributeError:
                        print("Error: Classifier model does not have 'predict_batch' method or requires different input format.")
                        return ["Error"] * len(crops), ["N/A"] * len(crops)
                    except Exception as e:
                        print(f"Error during classification prediction: {e}")
                        return ["Error"] * len(crops), ["N/A"] * len(crops)


            # Ensure lists have the same length as the number of boxes
            if len(classifications_list) != len(boxes):
                print(f"Warning: Mismatch between number of boxes ({len(boxes)}) and classifications ({len(classifications_list)}). Adjusting.")
                # Pad or truncate as necessary, or return error indication
                classifications_list.extend(["N/A"] * (len(boxes) - len(classifications_list)))
                severitys_list.extend(["N/A"] * (len(boxes) - len(severitys_list)))
                classifications_list = classifications_list[:len(boxes)]
                severitys_list = severitys_list[:len(boxes)]

            print("DEFECT DETECTION")
            print(classifications_list)
            print(severitys_list)
            print(self.model.idx_to_cls_map)

            return {"classification" : classifications_list,
                    "severity": severitys_list,
                    "class_idx": self.model.idx_to_cls_map
            }

        except Exception as e:
            print(f"Error in object detection: {e}")
            return {'error': str(e)}

    def _run_semantic_segmentation_og(self, image: Image.Image, threshold: float) -> Dict[str, Any]:
        """Run semantic segmentation inference."""
        try:
            print(f"Running semantic segmentation with threshold {threshold}")

            if self.model is None:
                raise ValueError("Model not initialized")

            with torch.no_grad():
                # Use the predict method from HFVisionModelWrapper
                resp = self.model.predict(image)

                # Post-process the response to get the segmentation map
                resp = self.model.preprocessor.post_process_semantic_segmentation(
                    resp, target_sizes=[image.size[::-1]]
                )

                # Get the segmentation mask
                mask_array = resp[0].cpu().detach().numpy()

                return {
                    'mask': mask_array,
                    'task_type': 'semantic_segmentation'
                }
        except Exception as e:
            print(f"Error in semantic segmentation: {e}")
            return {'error': str(e)}

    def _run_semantic_segmentation(
        self,
        image: Image.Image,
        conf_threshold: float = 0.5,
        background_class: int = 0,
    ) -> Dict[str, Any]:
        # Get image dimensions from first image
        if type(image) == Image.Image:
            original_images = image
        else:
            original_images = Image.fromarray(image)

        # Preprocess all images as a batch
        pixel_values = self.model.preprocessor(images=original_images, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.hf_model(**pixel_values)
        # Process the entire batch at once
        if "mask" in self.model.model_name:
            logits = self._get_mask2former_logits(outputs)
        else:
            logits = self._get_segformer_logits(outputs)

        mask_results = logits_to_mask(
            logits,
            conf_threshold,
            background_class,
            target_size=(original_images.size[1], original_images.size[0])
        )
        mask = mask_results[0].cpu().detach().numpy()

        return {
            'logits': logits,
            'mask': mask,
            'task_type': 'semantic_segmentation'
        }

    def _get_segformer_logits(self, outputs):
        logits = outputs["logits"]  # Shape: (batch, num_classes, H_orig, W_orig)
        return logits

    def _get_mask2former_logits(self, outputs):
        if hasattr(outputs, 'class_queries_logits') and hasattr(outputs, 'masks_queries_logits'):
            class_queries_logits = outputs.class_queries_logits  # [batch_size, num_queries, num_classes+1]
            masks_queries_logits = outputs.masks_queries_logits  # [batch_size, num_queries, height, width]
        else:
            class_queries_logits = outputs["pred_logits"]  # [batch_size, num_queries, num_classes+1]
            masks_queries_logits = outputs["pred_masks"]   # [batch_size, num_queries, height, width]

        # Remove the null class `[..., :-1]` and get class probabilities
        masks_classes = class_queries_logits.softmax(dim=-1)[..., :-1]  # [batch_size, num_queries, num_classes]
        masks_probs = masks_queries_logits.sigmoid()  # [batch_size, num_queries, height, width]

        # Semantic segmentation logits of shape (batch_size, num_classes, height, width)
        segmentation_logits = torch.einsum("bqc, bqhw -> bchw", masks_classes, masks_probs)
        return segmentation_logits

    def _mask_to_bounding_box(self, result: Dict[str, Any], min_area: int = 10) -> Dict[str, Any]:
        """Convert mask to bounding box format."""
        mask = result.get('mask')
        if mask is None:
            return result

        try:
            boxes = []
            scores = []
            labels = []

            # Get unique class IDs from the mask (excluding background class 0)
            unique_classes = np.unique(mask)
            unique_classes = unique_classes[unique_classes != 0]  # Exclude background

            for class_id in unique_classes:
                # Create binary mask for this class
                class_mask = (mask == class_id).astype(np.uint8)

                # Find contours for this class
                contours, _ = cv2.findContours(class_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for contour in contours:
                    # Filter out very small contours
                    if cv2.contourArea(contour) < min_area:  # Minimum area threshold
                        continue

                    # Get bounding rectangle
                    x, y, w, h = cv2.boundingRect(contour)
                    boxes.append([int(x), int(y), int(x + w), int(y + h)])

                    # Calculate confidence based on the proportion of the box that contains the class
                    box_mask = class_mask[y:y+h, x:x+w]
                    if box_mask.size > 0:
                        confidence = np.sum(box_mask) / box_mask.size
                    else:
                        confidence = 0.5

                    scores.append(confidence)
                    labels.append(int(class_id))

            return {
                'boxes': np.array(boxes) if boxes else np.array([]),
                'scores': np.array(scores) if scores else np.array([]),
                'labels': np.array(labels) if labels else np.array([]),
                'task_type': 'object_detection',
                'original_mask': mask,
                'logits': result.get('logits', None)
            }
        except Exception as e:
            print(f"Error converting mask to bounding box: {e}")
            return result

    def _bounding_box_to_mask(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Convert bounding box to mask format."""
        boxes = result.get('boxes')
        if boxes is None or len(boxes) == 0:
            return result

        try:
            # Get image size from first box (assuming all boxes are from same image)
            if len(boxes) > 0:
                max_x = max(box[2] for box in boxes)
                max_y = max(box[3] for box in boxes)
                mask = np.zeros((max_y, max_x), dtype=np.uint8)

                for box in boxes:
                    x1, y1, x2, y2 = box
                    mask[y1:y2, x1:x2] = 1

                return {
                    'mask': mask,
                    'task_type': 'semantic_segmentation',
                    'original_boxes': boxes
                }
        except Exception as e:
            print(f"Error converting bounding box to mask: {e}")
            return result

        return result

    def draw_detection_boxes(self, image: Image.Image, detection_result: Dict[str, Any]) -> Image.Image:
        """Draw bounding boxes on image for object detection."""
        if not detection_result or 'boxes' not in detection_result:
            return image

        img_array = np.array(image.convert("RGB"))

        boxes = detection_result['boxes']
        scores = detection_result['scores']
        labels = detection_result['labels']

        for i, (box, score, label) in enumerate(zip(boxes, scores, labels)):
            x1, y1, x2, y2 = map(int, box)

            # Get consistent color for this class
            color = self.get_consistent_color(int(label))
            color_bgr = tuple(reversed(color))

            # Draw bounding box
            cv2.rectangle(img_array, (x1, y1), (x2, y2), color_bgr, 2)

            # Add label with confidence
            label_text = f"Class {label}: {score:.2f}"

            # Calculate text size for background
            (text_width, text_height), baseline = cv2.getTextSize(
                label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
            )

            # Draw background rectangle for text
            cv2.rectangle(
                img_array,
                (x1, y1 - text_height - baseline - 5),
                (x1 + text_width, y1),
                color_bgr,
                -1
            )

            # Draw text
            cv2.putText(
                img_array,
                label_text,
                (x1, y1 - baseline - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),  # White text
                1
            )

        return Image.fromarray(img_array)

    def get_consistent_color(self, class_id: int) -> List[int]:
        """Get consistent color for a class ID."""
        fixed_colors = [
            [0, 0, 0],        # Class 0: Black (background)
            [255, 0, 0],      # Class 1: Red
            [0, 255, 0],      # Class 2: Green
            [0, 0, 255],      # Class 3: Blue
            [255, 255, 0],    # Class 4: Yellow
            [255, 0, 255],    # Class 5: Magenta
            [0, 255, 255],    # Class 6: Cyan
            [255, 165, 0],    # Class 7: Orange
            [128, 0, 128],    # Class 8: Purple
            [255, 192, 203],  # Class 9: Pink
            [128, 128, 128],  # Class 10: Gray
            [165, 42, 42],    # Class 11: Brown
            [0, 128, 0],      # Class 12: Dark Green
            [128, 0, 0],      # Class 13: Dark Red
            [0, 0, 128],      # Class 14: Dark Blue
            [255, 215, 0],    # Class 15: Gold
        ]

        if class_id < len(fixed_colors):
            return fixed_colors[class_id]
        else:
            np.random.seed(class_id)
            color = np.random.randint(0, 255, 3).tolist()
            np.random.seed()
            return color

    def generate_colored_mask(self, mask_array: np.ndarray) -> np.ndarray:
        """Generate colored mask using consistent colors."""
        unique_classes = np.unique(mask_array)
        colored_mask = np.zeros((*mask_array.shape, 3), dtype=np.uint8)

        for class_id in unique_classes:
            color = self.get_consistent_color(class_id)
            colored_mask[mask_array == class_id] = color

        return colored_mask

    def create_segmentation_overlay(self, image: Image.Image, mask_array: np.ndarray, alpha: float = 0.5) -> Image.Image:
        """Create overlay of image and colored segmentation mask."""
        try:
            img_array = np.array(image.convert("RGB"))
            colored_mask = self.generate_colored_mask(mask_array)

            # Resize mask to match image if needed
            if colored_mask.shape[:2] != img_array.shape[:2]:
                colored_mask = cv2.resize(colored_mask, (img_array.shape[1], img_array.shape[0]))

            # Create overlay
            overlay = cv2.addWeighted(img_array, 1-alpha, colored_mask, alpha, 0)
            return Image.fromarray(overlay)
        except Exception as e:
            print(f"Error creating segmentation overlay: {str(e)}")
            return image
