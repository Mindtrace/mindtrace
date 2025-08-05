import os
import sys
import yaml
import json
import torch
import numpy as np
from typing import Optional, Dict, Any, Tuple, List, Union
from enum import Enum
from PIL import Image
import cv2
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from mindtrace.automation.modelling.mig_model_inference import ModelInference, ExportType
from mindtrace.storage.gcs import GCSStorageHandler
from mindtrace.automation.modelling.utils import crop_zones, combine_crops, logits_to_mask, get_updated_key




class MIGPipeline:
    """Pipeline class to manage multiple models for inference."""

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        bucket_name: str = '',
        base_folder: str = '',
        local_models_dir: str = "./tmp"
    ):


        if not bucket_name:
            raise ValueError("bucket_name must be provided")
        if not base_folder:
            raise ValueError("base_folder must be provided")

        self.credentials_path = credentials_path
        self.bucket_name = bucket_name
        self.base_folder = base_folder
        self.local_models_dir = local_models_dir
        self.device = self._get_device()


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

            except Exception as e:
                print(f"Error loading pipeline: {e}")
                return False

            # Load pipeline metadata
            # pipeline_metadata = self._load_pipeline_metadata(task_name, version)
            # if pipeline_metadata is None:
            #     return False

            for inference_task, export_type in inference_list.items():
                if not self._load_model(task_name, version, inference_task, export_type):
                    print(f"Failed to load model for task: {inference_task}")
                    return False

    def _download_pipeline_if_needed(self, task_name: str, version: str) -> bool:

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

            model_name = model_metadata.get('model_type', 'unknown')
            task_type = model_metadata.get('task', 'object_detection')

            # Create ModelInference instance
            model_inference = ModelInference(
                model_path=model_path,
                task_type=task_type,
                model_name=model_name,
                device=self.device,
                inference_task=inference_task,
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


    def run_inference_on_folder(
        self,
        input_folder: str,
        output_folder: str,
        export_types: Optional[Dict[str, ExportType]] = None,
        threshold: float = 0.4,
        save_visualizations: bool = True,
        supported_formats: Tuple[str, ...] = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'),
        num_workers: int = 4) -> Dict[str, Any]:
        """Run inference concurrently on all images in a folder and its subfolders.

        Args:
            input_folder: Path to folder containing images
            output_folder: Path to save results and visualizations
            export_types: Dictionary mapping task names to export types
            threshold: Confidence threshold for detections
            save_visualizations: Whether to save visualization images
            supported_formats: Image formats to process
            num_workers: Number of worker threads for concurrent processing

        Returns:
            Dictionary with results summary
        """
        if not os.path.exists(input_folder):
            raise ValueError(f"Input folder does not exist: {input_folder}")

        # Create output folder structure
        os.makedirs(output_folder, exist_ok=True)
        images_folder = os.path.join(output_folder, "images")
        boxes_folder = os.path.join(output_folder, "boxes")
        visualizations_folder = os.path.join(output_folder, "visualizations")

        os.makedirs(images_folder, exist_ok=True)
        os.makedirs(boxes_folder, exist_ok=True)
        os.makedirs(visualizations_folder, exist_ok=True)

        # Get list of image files from all subfolders
        image_files = []
        for root, _, files in os.walk(input_folder):
            for file in files:
                if file.lower().endswith(supported_formats):
                    image_files.append(os.path.join(root, file))

        if not image_files:
            print(f"No supported image files found in {input_folder} or its subfolders")
            return {'error': 'No supported images found'}

        print(f"Found {len(image_files)} images to process in {input_folder} and its subfolders using {num_workers} workers.")

        results_summary = {
            'total_images': len(image_files),
            'processed_images': 0,
            'failed_images': 0,
            'results': {}
        }

        def _process_image(image_path):
            try:
                print(f"Processing image: {os.path.basename(image_path)} (from {os.path.dirname(image_path)})")

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

                print("******")
                print(results)
                # Save structured outputs
                image_name = os.path.splitext(os.path.basename(image_path))[0]

                print("DEBUGGING")
                print(type(boxes_folder))
                self._save_structured_outputs(image_path, results, boxes_folder, export_types)

                # Save visualizations if requested
                if save_visualizations:
                    self._save_visualizations(image_path, results, visualizations_folder, image_name, export_types)

                return image_name, None
            except Exception as e:
                print(f"Error processing {image_path}: {e}")
                return os.path.splitext(os.path.basename(image_path))[0], str(e)

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Use executor.map to preserve order
            results_iterator = executor.map(_process_image, image_files)

            # Iterate over results which are now in order
            for image_name, error in tqdm(results_iterator, total=len(image_files), desc="Processing images"):
                if error is None:
                    results_summary['processed_images'] += 1
                else:
                    results_summary['failed_images'] += 1
                    results_summary['results'][image_name] = {'error': error}

        print(f"Inference completed: {results_summary['processed_images']} processed, {results_summary['failed_images']} failed")
        return results_summary


    def run_inference_on_models(
        self,
        image: Union[str, Image.Image, np.ndarray],
        export_types: Optional[Dict[str, ExportType]] = None,
        threshold: float = 0.4,
        follow_pipeline: bool = False,
    ) -> Dict[str, Any]:
        """Run inference on all loaded models.

        Args:
            image: Input image
            export_types: Dictionary mapping task names to export types
                         If None, uses default export types from inference_list
            threshold: Confidence threshold for detections
            follow_pipeline: Whether to follow the pipeline order
        Returns:
            Dictionary with results for each model
        """
        results = {}
        if not follow_pipeline:
            for task_name, model in self.models.items():
                try:
                    # Determine export type
                    export_type = ExportType.BOUNDING_BOX  # Default
                    if export_types and task_name in export_types:
                        export_type = export_types[task_name]


                    result = model.run_inference(
                        image=image,
                        export_type=export_type,
                        threshold=threshold,
                    )

                    results[task_name] = result
                    print(f"Inference completed for {task_name}")

                except Exception as e:
                    print(f"Error running inference for {task_name}: {e}")
                    results[task_name] = {'error': str(e)}

            return results



    def _save_structured_outputs(self, image_path: str, results: Dict[str, Any],
                                boxes_folder: str,
                               export_types: Optional[Dict[str, ExportType]] = None,
                               ):
        """Save raw masks and YOLO format boxes with original image filename."""
        try:
            print("DEBUGGING")
            print(type(boxes_folder))
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



                # Save YOLO format boxes with original filename
                if 'boxes' in result:


                    task_boxes_folder = os.path.join(boxes_folder, str(task_name))

                    os.makedirs(task_boxes_folder, exist_ok=True)
                    boxes = result['boxes']


                    # Use original image filename for boxes
                    boxes_filename = f"{image_name}.txt"
                    boxes_path = os.path.join(task_boxes_folder, boxes_filename)

                    print("BOXES")
                    print(boxes)
                    with open(boxes_path, 'w') as f:

                        if len(boxes[0][0]) == 7:
                            f.write(f"{boxes[0][0][5]} {boxes[0][0][6]} {boxes[0][0][0]:.6f} {boxes[0][0][1]:.6f} {boxes[0][0][2]:.6f} {boxes[0][0][3]:.6f} {boxes[0][0][4]:.6f}\n")

                        else:
                             f.write(f"Not enough data\n")


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