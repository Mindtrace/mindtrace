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
from mindtrace.storage.gcs import GCSStorageHandler


class ExportType(Enum):
    """Export format types for inference results."""
    BOUNDING_BOX = "bounding_box"
    MASK = "mask"


class ModelInference:
    """Individual model inference class for a specific task."""
    
    def __init__(
        self,
        model_path: str,
        task_type: str,
        model_name: str,
        device: str = "cpu"
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
            print(f"Loaded {len(self.id2label)} class labels")
        except Exception as e:
            print(f"Error loading id2label: {e}")
            self.id2label = {}
    
    def _instantiate_model(self):
        """Instantiate the model using HFVisionModelWrapper."""
        try:
            print(f"Instantiating model: {self.model_name} for task: {self.task_type}")
            print(f"Model path: {self.model_path}")            

            self.model = HFVisionModelWrapper(
                model_name=self.model_name,
                task=self.task_type,
                checkpoint_path=self.model_path
            )
            
            self.model.to(self.device)
            
            print(f"Model instantiated successfully")
        except Exception as e:
            print(f"Error instantiating model: {e}")
            self.model = None
    
    def run_inference(self, image: Union[str, Image.Image, np.ndarray], 
                     export_type: ExportType = ExportType.BOUNDING_BOX,
                     threshold: float = 0.5) -> Dict[str, Any]:
        """Run inference on the image.
        
        Args:
            image: Input image (path, PIL Image, or numpy array)
            export_type: Export format (bounding_box or mask)
            threshold: Confidence threshold for detections
            
        Returns:
            Dictionary with inference results, preserving both mask and box information when available
        """
        if self.model is None:
            raise ValueError("Model not initialized")
        
        # Convert image to PIL if needed
        if isinstance(image, str):
            image = Image.open(image).convert('RGB')
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image).convert('RGB')
        
        # Run task-specific inference
        if self.task_type == "object_detection":
            result = self._run_object_detection(image, threshold)
        elif self.task_type in ["semantic_segmentation", "universal_segmentation"]:
            result = self._run_semantic_segmentation(image, threshold)
        else:
            raise ValueError(f"Unsupported task type: {self.task_type}")
        
        # Convert to requested export format while preserving original information
        if export_type == ExportType.BOUNDING_BOX and result.get('mask') is not None:
            box_result = self._mask_to_bounding_box(result)
            result = {
                'mask': result['mask'],  # Keep original mask
                'boxes': box_result.get('boxes', np.array([])),
                'scores': box_result.get('scores', np.array([])),
                'labels': box_result.get('labels', np.array([])),
                'task_type': result['task_type']
            }
        elif export_type == ExportType.MASK and result.get('boxes') is not None:
            mask_result = self._bounding_box_to_mask(result)
            result = {
                'mask': mask_result.get('mask'),
                'boxes': result.get('boxes', np.array([])),  # Keep original boxes
                'scores': result.get('scores', np.array([])),
                'labels': result.get('labels', np.array([])),
                'task_type': result['task_type']
            }
        
        return result
    
    def _run_object_detection(self, image: Image.Image, threshold: float) -> Dict[str, Any]:
        """Run object detection inference."""
        try:
            print(f"Running object detection with threshold {threshold}")
            
            if self.model is None:
                raise ValueError("Model not initialized")
            
            with torch.no_grad():
                resp = self.model.predict(image)
                
            resp = self.model.preprocessor.post_process_object_detection(
                resp, 
                threshold=threshold, 
                target_sizes=[image.size[::-1]]
            )
            
            if resp and len(resp) > 0 and 'boxes' in resp[0]:
                boxes = resp[0]['boxes'].cpu().numpy() if hasattr(resp[0]['boxes'], 'cpu') else resp[0]['boxes']
                scores = resp[0]['scores'].cpu().numpy() if hasattr(resp[0]['scores'], 'cpu') else resp[0]['scores']
                labels = resp[0]['labels'].cpu().numpy() if hasattr(resp[0]['labels'], 'cpu') else resp[0]['labels']
                
                return {
                    'boxes': boxes,
                    'scores': scores,
                    'labels': labels,
                    'task_type': 'object_detection'
                }
            return {'error': 'No detections found'}
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
            # Convert numpy arrays to PIL Images for overlay if needed
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

        mask_results = self.logits_to_mask(
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

    def logits_to_mask(self, logits, conf_threshold, background_class, target_size=None):
        probs = torch.softmax(logits, dim=1)
        mask_pred = torch.argmax(probs, dim=1)

        if conf_threshold > 0:
            max_probs = torch.max(probs, dim=1)[0]
            low_confidence_mask = max_probs < conf_threshold
            if mask_pred.shape != low_confidence_mask.shape:
                try:
                    low_confidence_mask = low_confidence_mask.view(mask_pred.shape)
                except Exception as e:
                    print(f"Error reshaping low_confidence_mask: {e}")
                    raise
            mask_pred[low_confidence_mask] = background_class

        if target_size is not None:
            mask_pred = mask_pred.unsqueeze(1).float()
            mask_pred = torch.nn.functional.interpolate(
                mask_pred, size=target_size, mode="nearest"
            )
            mask_pred = mask_pred.squeeze(1).long()
            
        return mask_pred
        
        
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
            
            # Add boxes to the result, but keep the original mask
            result['boxes'] = np.array(boxes) if boxes else np.array([])
            result['scores'] = np.array(scores) if scores else np.array([])
            result['labels'] = np.array(labels) if labels else np.array([])
            return result

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


class Pipeline:
    """Pipeline class to manage multiple models for inference."""
    
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        bucket_name: str = '',
        base_folder: str = '',
        local_models_dir: str = "./tmp",
        overwrite_masks: bool = False
    ):
        """Initialize the pipeline.
        
        Args:
            credentials_path: Path to GCP credentials file
            bucket_name: GCS bucket name (must be provided)
            base_folder: Base folder in the bucket (must be provided)
            local_models_dir: Local directory to store downloaded models
            overwrite_masks: Whether to overwrite masks or save in task subfolders
        """
        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        if not base_folder:
            raise ValueError("base_folder must be provided")
            
        self.credentials_path = credentials_path
        self.bucket_name = bucket_name
        self.base_folder = base_folder
        self.local_models_dir = local_models_dir
        self.overwrite_masks = overwrite_masks
        self.device = self._get_device()
        
        # Initialize GCS storage handler
        if GCSStorageHandler is None:
            raise ImportError("GCSStorageHandler is not available. Please check your imports.")
        self.storage_handler = GCSStorageHandler(
            bucket_name=bucket_name,
            credentials_path=credentials_path
        )
        
        # Store loaded models
        self.models: Dict[str, ModelInference] = {}
    
    def _get_device(self) -> str:
        """Get the best available device for inference."""
        if torch.cuda.is_available():
            return "cuda:0"
        else:
            return "cpu"
    
    def load_pipeline(self, task_name: str, version: str, 
                     inference_list: Dict[str, str]) -> bool:
        """Load a pipeline with multiple models.
        
        Args:
            task_name: Name of the pipeline task (e.g., 'sfz_pipeline')
            version: Version to load (e.g., 'v2.1')
            inference_list: Dictionary mapping task names to export types
                          e.g., {"zone_segmentation": "bounding_box", "spatter_segmentation": "mask"}
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Download the pipeline if needed
            if not self._download_pipeline_if_needed(task_name, version):
                return False
            
            # Load pipeline metadata
            pipeline_metadata = self._load_pipeline_metadata(task_name, version)
            if pipeline_metadata is None:
                return False
            
            # Load each model in the inference list
            for inference_task, export_type in inference_list.items():
                if not self._load_model(task_name, version, inference_task, export_type):
                    print(f"Failed to load model for task: {inference_task}")
                    return False
            
            print(f"Successfully loaded pipeline {task_name} v{version} with {len(self.models)} models")
            return True
            
        except Exception as e:
            print(f"Error loading pipeline: {e}")
            return False
    
    def _download_pipeline_if_needed(self, task_name: str, version: str) -> bool:
        """Download pipeline if it doesn't exist locally."""
        pipeline_path = os.path.join(self.local_models_dir, task_name, version)
        metadata_path = os.path.join(pipeline_path, "metadata.json")
        
        if os.path.exists(metadata_path):
            print(f"Pipeline {task_name} v{version} already exists locally")
            return True
        
        try:
            print(f"Downloading pipeline {task_name} v{version}...")
            downloaded_files, actual_version = self.storage_handler.download_model_from_registry(
                task_name=task_name,
                local_directory=self.local_models_dir,
                version=version,
                credentials_path=self.credentials_path,
                base_folder=self.base_folder,
                overwrite=False
            )
            print(f"Downloaded {len(downloaded_files)} files for pipeline {task_name} v{actual_version}")
            return True
        except Exception as e:
            print(f"Failed to download pipeline: {e}")
            return False
    
    def _load_pipeline_metadata(self, task_name: str, version: str) -> Optional[Dict[str, Any]]:
        """Load pipeline metadata."""
        metadata_path = os.path.join(self.local_models_dir, task_name, version, "metadata.json")
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            print(f"Loaded pipeline metadata: {metadata}")
            return metadata
        except Exception as e:
            print(f"Error loading pipeline metadata: {e}")
            return None
    
    def _load_model(self, task_name: str, version: str, inference_task: str, 
                   export_type: str) -> bool:
        """Load a specific model from the pipeline."""
        try:
            model_path = os.path.join(self.local_models_dir, task_name, version, inference_task)
            
            # Load model metadata
            model_metadata_path = os.path.join(model_path, "metadata.json")
            if not os.path.exists(model_metadata_path):
                print(f"Model metadata not found: {model_metadata_path}")
                return False
            
            with open(model_metadata_path, 'r') as f:
                model_metadata = json.load(f)
            
            model_name = model_metadata.get('model_name', 'unknown')
            task_type = model_metadata.get('task', 'unknown')
            
            # Create ModelInference instance
            model_inference = ModelInference(
                model_path=model_path,
                task_type=task_type,
                model_name=model_name,
                device=self.device
            )
            
            # Store with export type
            self.models[inference_task] = model_inference
            print(f"Loaded model {inference_task}: {model_name} ({task_type})")
            return True
            
        except Exception as e:
            print(f"Error loading model {inference_task}: {e}")
            return False
    
    def run_inference_on_path(self, 
                     input_path: str,
                     output_folder: str,
                     export_types: Optional[Dict[str, ExportType]] = None,
                     threshold: float = 0.4,
                     save_visualizations: bool = True,
                     supported_formats: Tuple[str, ...] = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')) -> Dict[str, Any]:
        """Run inference on a single image or all images in a folder (including subfolders).
        
        Args:
            input_path: Path to single image or folder containing images
            output_folder: Path to save results and visualizations
            export_types: Dictionary mapping task names to export types
            threshold: Confidence threshold for detections
            save_visualizations: Whether to save visualization images
            supported_formats: Image formats to process
            
        Returns:
            Dictionary with results summary
        """
        if not os.path.exists(input_path):
            raise ValueError(f"Input path does not exist: {input_path}")
        
        if os.path.isfile(input_path):
            # Single image
            return self._run_inference_on_single_image(
                input_path, output_folder, export_types, threshold, save_visualizations
            )
        elif os.path.isdir(input_path):
            # Folder (with subfolder support)
            return self.run_inference_on_folder(
                input_path, output_folder, export_types, threshold, save_visualizations, supported_formats
            )
        else:
            raise ValueError(f"Input path is neither a file nor directory: {input_path}")
    
    def _run_inference_on_single_image(self, 
                                      image_path: str,
                                      output_folder: str,
                                      export_types: Optional[Dict[str, ExportType]] = None,
                                      threshold: float = 0.4,
                                      save_visualizations: bool = True) -> Dict[str, Any]:
        """Run inference on a single image.
        
        Args:
            image_path: Path to the image file
            output_folder: Path to save results and visualizations
            export_types: Dictionary mapping task names to export types
            threshold: Confidence threshold for detections
            save_visualizations: Whether to save visualization images
            
        Returns:
            Dictionary with results summary
        """
        # Create output folder structure
        os.makedirs(output_folder, exist_ok=True)
        images_folder = os.path.join(output_folder, "images")
        raw_masks_folder = os.path.join(output_folder, "raw_masks") 
        boxes_folder = os.path.join(output_folder, "boxes")
        visualizations_folder = os.path.join(output_folder, "visualizations")
        
        os.makedirs(images_folder, exist_ok=True)
        os.makedirs(raw_masks_folder, exist_ok=True)
        os.makedirs(boxes_folder, exist_ok=True)
        os.makedirs(visualizations_folder, exist_ok=True)
        
        try:
            print(f"Processing single image: {os.path.basename(image_path)}")
            
            # Copy original image to images folder
            image_filename = os.path.basename(image_path)
            image_dest = os.path.join(images_folder, image_filename)
            shutil.copy2(image_path, image_dest)
            
            # Run inference on all models
            results = self.run_inference_on_models(
                image=image_path,
                export_types=export_types,
                threshold=threshold
            )
            
            # Save structured outputs
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            self._save_structured_outputs(image_path, results, raw_masks_folder, boxes_folder, export_types, self.overwrite_masks)
            
            # Save visualizations if requested
            if save_visualizations:
                self._save_visualizations(image_path, results, visualizations_folder, image_name, export_types)
            
            results_summary = {
                'total_images': 1,
                'processed_images': 1,
                'failed_images': 0,
                'results': {image_name: results}
            }
            
            print(f"Single image inference completed successfully")
            return results_summary
            
        except Exception as e:
            print(f"Error processing {image_path}: {e}")
            return {
                'total_images': 1,
                'processed_images': 0,
                'failed_images': 1,
                'results': {},
                'error': str(e)
            }

    def run_inference_on_folder(self, 
                               input_folder: str,
                               output_folder: str,
                               export_types: Optional[Dict[str, ExportType]] = None,
                               threshold: float = 0.4,
                               save_visualizations: bool = True,
                               supported_formats: Tuple[str, ...] = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')) -> Dict[str, Any]:
        """Run inference on all images in a folder and its subfolders.
        
        Args:
            input_folder: Path to folder containing images
            output_folder: Path to save results and visualizations
            export_types: Dictionary mapping task names to export types
            threshold: Confidence threshold for detections
            save_visualizations: Whether to save visualization images
            supported_formats: Image formats to process
            
        Returns:
            Dictionary with results summary
        """
        if not os.path.exists(input_folder):
            raise ValueError(f"Input folder does not exist: {input_folder}")
        
        # Create output folder structure
        os.makedirs(output_folder, exist_ok=True)
        images_folder = os.path.join(output_folder, "images")
        raw_masks_folder = os.path.join(output_folder, "raw_masks") 
        boxes_folder = os.path.join(output_folder, "boxes")
        visualizations_folder = os.path.join(output_folder, "visualizations")
        
        os.makedirs(images_folder, exist_ok=True)
        os.makedirs(raw_masks_folder, exist_ok=True)
        os.makedirs(boxes_folder, exist_ok=True)
        os.makedirs(visualizations_folder, exist_ok=True)
        
        # Get list of image files from all subfolders
        image_files = []
        for root, dirs, files in os.walk(input_folder):
            for file in files:
                if file.lower().endswith(supported_formats):
                    image_files.append(os.path.join(root, file))
        
        if not image_files:
            print(f"No supported image files found in {input_folder} or its subfolders")
            return {'error': 'No supported images found'}
        
        print(f"Found {len(image_files)} images to process in {input_folder} and its subfolders")
        
        # Process each image
        results_summary = {
            'total_images': len(image_files),
            'processed_images': 0,
            'failed_images': 0,
            'results': {}
        }
        
        for i, image_path in enumerate(image_files):
            try:
                print(f"Processing image {i+1}/{len(image_files)}: {os.path.basename(image_path)} (from {os.path.dirname(image_path)})")
                
                # Copy original image to images folder
                image_filename = os.path.basename(image_path)
                image_dest = os.path.join(images_folder, image_filename)
                shutil.copy2(image_path, image_dest)
                
                # Run inference
                results = self.run_inference_on_models(
                    image=image_path,
                    export_types=export_types,
                    threshold=threshold
                )
                
                # Save structured outputs
                image_name = os.path.splitext(os.path.basename(image_path))[0]
                self._save_structured_outputs(image_path, results, raw_masks_folder, boxes_folder, export_types, self.overwrite_masks)
                
                # Save visualizations if requested
                if save_visualizations:
                    self._save_visualizations(image_path, results, visualizations_folder, image_name, export_types)
                
                results_summary['results'][image_name] = results
                results_summary['processed_images'] += 1
                
            except Exception as e:
                print(f"Error processing {image_path}: {e}")
                results_summary['failed_images'] += 1
        
        print(f"Inference completed: {results_summary['processed_images']} processed, {results_summary['failed_images']} failed")
        return results_summary
    
    def get_loaded_models(self) -> List[str]:
        """Get list of loaded model names."""
        return list(self.models.keys())
    
    def get_model_info(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific model."""
        if task_name not in self.models:
            return None
        model = self.models[task_name]
        return {
            'model_name': model.model_name,
            'task_type': model.task_type,
            'model_path': model.model_path,
            'device': model.device,
            'img_size': model.img_size,
            'num_classes': len(model.id2label),
            'id2label': model.id2label
        }
    
    def run_inference_on_models(self, image: Union[str, Image.Image, np.ndarray],
                     export_types: Optional[Dict[str, ExportType]] = None,
                     threshold: float = 0.4) -> Dict[str, Any]:
        """Run inference on all loaded models.
        
        Args:
            image: Input image
            export_types: Dictionary mapping task names to export types
                         If None, uses default export types from inference_list
            threshold: Confidence threshold for detections
        
        Returns:
            Dictionary with results for each model
        """
        results = {}
        
        for task_name, model_inference in self.models.items():
            try:
                # Determine export type
                export_type = ExportType.BOUNDING_BOX  # Default
                if export_types and task_name in export_types:
                    export_type = export_types[task_name]
                
                # Run inference
                result = model_inference.run_inference(
                    image=image,
                    export_type=export_type,
                    threshold=threshold
                )
                
                results[task_name] = result
                print(f"Inference completed for {task_name}")
                
            except Exception as e:
                print(f"Error running inference for {task_name}: {e}")
                results[task_name] = {'error': str(e)}
        
        return results

    def _make_json_serializable(self, obj):
        """Convert numpy arrays and other non-serializable objects to JSON-serializable formats."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, dict):
            return {key: self._make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif hasattr(obj, 'cpu') and hasattr(obj, 'numpy'):  # Handle torch tensors
            return obj.cpu().numpy().tolist()
        else:
            return obj

    def _save_structured_outputs(self, image_path: str, results: Dict[str, Any], 
                               raw_masks_folder: str, boxes_folder: str,
                               export_types: Optional[Dict[str, ExportType]] = None,
                               overwrite_masks: bool = False):
        """Save raw masks and YOLO format boxes with original image filename."""
        try:
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            image_extension = os.path.splitext(os.path.basename(image_path))[1]
            
            # Load original image to get dimensions for YOLO format
            original_image = Image.open(image_path).convert('RGB')
            img_width, img_height = original_image.size
            
            results = self._make_json_serializable(results)
            
            for task_name, result in results.items():
                if not result or 'error' in result:
                    continue
                
                current_export_type = export_types.get(task_name) if export_types else None

                # Save id2label as yaml
                model_info = self.get_model_info(task_name)
                if model_info and model_info.get('id2label'):
                    id2label_map = {int(k): v for k, v in model_info['id2label'].items()}
                    
                    output_dir = None
                    if current_export_type == ExportType.MASK:
                        output_dir = os.path.join(raw_masks_folder, task_name)
                    elif current_export_type == ExportType.BOUNDING_BOX:
                        output_dir = os.path.join(boxes_folder, task_name)
                    
                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        yaml_path = os.path.join(output_dir, 'id2label.yaml')
                        if not os.path.exists(yaml_path):
                            with open(yaml_path, 'w') as f:
                                yaml.dump(id2label_map, f, default_flow_style=False)
                            print(f"Saved id2label map to {yaml_path}")

                # Save raw masks - save masks whenever they exist, regardless of export type
                if 'mask' in result:
                    mask = np.array(result['mask'])
                    if mask is not None and mask.size > 0:
                        # Determine where to save based on export type or default to mask folder
                        if current_export_type == ExportType.MASK:
                            if overwrite_masks:
                                # Overwrite mode: use original image filename
                                mask_filename = f"{image_name}.png"
                                raw_mask_path = os.path.join(raw_masks_folder, mask_filename)
                            else:
                                # Non-overwrite mode: create task subfolder
                                task_mask_folder = os.path.join(raw_masks_folder, task_name)
                                os.makedirs(task_mask_folder, exist_ok=True)
                                mask_filename = f"{image_name}.png"
                                raw_mask_path = os.path.join(task_mask_folder, mask_filename)
                        else:
                            # For bounding box export type, always save in task subfolder
                            task_mask_folder = os.path.join(raw_masks_folder, task_name)
                            os.makedirs(task_mask_folder, exist_ok=True)
                            mask_filename = f"{image_name}.png"
                            raw_mask_path = os.path.join(task_mask_folder, mask_filename)
                        
                        mask = mask.astype(np.uint8)
                        
                        # Save the raw mask as PNG (preserves class values)
                        mask_pil = Image.fromarray(mask, mode='L' if mask.dtype == np.uint8 else 'I;16')
                        mask_pil.save(raw_mask_path)
                        print(f"Saved raw mask: {raw_mask_path}")
                
                # Save YOLO format boxes with original filename  
                if 'boxes' in result:
                    task_boxes_folder = os.path.join(boxes_folder, task_name)
                    os.makedirs(task_boxes_folder, exist_ok=True)
                    boxes = result['boxes']
                    scores = result.get('scores', [])
                    labels = result.get('labels', [])
                    
                    # Use original image filename for boxes
                    boxes_filename = f"{image_name}.txt"
                    boxes_path = os.path.join(task_boxes_folder, boxes_filename)
                    
                    # Always save the file, even if no boxes detected
                    self._save_yolo_boxes(boxes, scores, labels, boxes_path, img_width, img_height)
                    if len(boxes) > 0:
                        print(f"Saved YOLO boxes: {boxes_path}")
                    else:
                        print(f"Saved empty YOLO boxes file: {boxes_path}")
        
        except Exception as e:
            print(f"Error saving structured outputs: {e}")
    
    def _save_yolo_boxes(self, boxes: np.ndarray, scores: np.ndarray, labels: np.ndarray, 
                        output_path: str, img_width: int, img_height: int):
        """Save bounding boxes in YOLO format with original coordinates (not normalized)."""
        try:
            with open(output_path, 'w') as f:
                for i, box in enumerate(boxes):
                    x1, y1, x2, y2 = box
                    
                    # Convert to YOLO format but keep original coordinates (not normalized)
                    # YOLO format: class_id center_x center_y width height
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    width = x2 - x1
                    height = y2 - y1
                    
                    # Get class id and confidence
                    class_id = int(labels[i]) if i < len(labels) else 0
                    confidence = scores[i] if i < len(scores) else 1.0
                    
                    # Write in YOLO format: class_id center_x center_y width height confidence
                    # Note: Using original coordinates, not normalized to [0,1]
                    f.write(f"{class_id} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f} {confidence:.6f}\n")
        
        except Exception as e:
            print(f"Error saving YOLO boxes: {e}")

    def _save_visualizations(self, image_path: str, results: Dict[str, Any], 
                           visualizations_folder: str, image_name: str, 
                           export_types: Optional[Dict[str, ExportType]] = None):
        """Save visualization images for each model result based on export types."""
        
            
        # Load original image
        original_image = Image.open(image_path).convert('RGB')
        
        for task_name, result in results.items():

            if 'error' in result:
                continue
            
            # Save bounding box visualization if boxes are present
            if 'boxes' in result and len(result.get('boxes', [])) > 0:
                box_vis_image = self.models[task_name].draw_detection_boxes(original_image.copy(), result)
                box_vis_path = os.path.join(visualizations_folder, f"{image_name}_{task_name}_boxes.jpg")
                box_vis_image.save(box_vis_path)

            # Save mask visualizations if a mask is present
            if 'mask' in result and result.get('mask') is not None and result['mask'].size > 0:
                try:
                    # Create overlay
                    mask_overlay_image = self.models[task_name].create_segmentation_overlay(original_image.copy(), result['mask'])
                    overlay_path = os.path.join(visualizations_folder, f"{image_name}_{task_name}_mask_overlay.jpg")
                    mask_overlay_image.save(overlay_path)
                    
                    # Also save colored mask only
                    colored_mask = self.models[task_name].generate_colored_mask(result['mask'])
                    mask_image = Image.fromarray(colored_mask)
                    mask_path = os.path.join(visualizations_folder, f"{image_name}_{task_name}_mask_colored.jpg")
                    mask_image.save(mask_path)
                except Exception as e:
                    print(f"Error saving mask visualizations: {str(e)}")

def test_pipeline():
    """Test function to verify pipeline functionality."""

    parser = argparse.ArgumentParser(description="Efficiently download images using database and GCS")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()
    
    with open(args.config) as f:
        config = yaml.safe_load(f)

    # Configuration
    credentials_path = config['gcp']['credentials_file']
    bucket_name = config['gcp']['weights_bucket']
    base_folder = config['gcp']['base_folder']
    input_folder = config['download_path']
    output_folder = config['output_folder']

    try:
        # Initialize pipeline
        pipeline = Pipeline(
            credentials_path=credentials_path,
            bucket_name=bucket_name,
            base_folder=base_folder,
            local_models_dir="./tmp",
            overwrite_masks=config['overwrite_masks']
        )

        # Test pipeline loading
        inference_list = config['inference_list']

        success = pipeline.load_pipeline(
            task_name=config['task_name'],
            version=config['version'],
            inference_list=inference_list
        )

        if not success:
            print("Failed to load pipeline")
            return

        # Test model info
        loaded_models = pipeline.get_loaded_models()

        for model_name in loaded_models:
            info = pipeline.get_model_info(model_name)
            print(f"Model {model_name}: {info}")

        # Test folder inference
        if os.path.exists(input_folder):
            # Convert string export types to ExportType enum values
            export_types = {}
            for task_name, export_type_str in config['inference_list'].items():
                if export_type_str == "mask":
                    export_types[task_name] = ExportType.MASK
                elif export_type_str == "bounding_box":
                    export_types[task_name] = ExportType.BOUNDING_BOX

            summary = pipeline.run_inference_on_folder(
                input_folder=input_folder,
                output_folder=output_folder,
                export_types=export_types,
                threshold=config['threshold'],
                save_visualizations=True
            )

        else:
            print(f"Input folder not found: {input_folder}")
            print("Skipping folder inference test")


    except ValueError as e:
        print(f"Configuration error: {e}")
    except ImportError as e:
        print(f"Import error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    test_pipeline()
