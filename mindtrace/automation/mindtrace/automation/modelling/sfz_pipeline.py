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
from mindtrace.automation.modelling import ModelInference, ExportType
from mindtrace.storage.gcs import GCSStorageHandler
from mindtrace.automation.modelling.utils import crop_zones, combine_crops, logits_to_mask

class SFZPipeline:
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
            
            self.get_reference_masks(task_name, version)
            cropping_path = os.path.join(
                self.local_models_dir, 
                task_name,
                version,
                'cropping.json'
            )
            if os.path.exists(cropping_path):
                self.cropping_config = json.load(open(cropping_path))
            else:
                print(f"DEBUG: File not found at {cropping_path}")
                self.cropping_config = None
            
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
    
    def get_reference_masks(self, task_name: str, version: str):
        self.reference_masks = {}
        reference_mask_folder = os.path.join(
            self.local_models_dir, 
            task_name,
            version,
            'zone_segmentation/reference_masks'
        )
        if os.path.exists(reference_mask_folder):
            for file in os.listdir(reference_mask_folder):
                if file.endswith('.png'):
                    mask = cv2.imread(os.path.join(reference_mask_folder, file))[:,:,0]
                    # mask = cv2.resize(mask, (128, 128), interpolation=cv2.INTER_NEAREST)
                    mask = torch.from_numpy(mask)
                    if self.device != 'cpu':
                        mask = mask.to(self.device)
                    self.reference_masks[file.split('.')[0].replace('_mask', '')] = mask
                else:
                    raise FileNotFoundError(f"Reference Mask format is not supported: {file}")
        else:
            raise FileNotFoundError(f"Reference Masks not found at {reference_mask_folder}")
        
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
    
    def run_inference_on_models(
        self, 
        image: Union[str, Image.Image, np.ndarray],
        export_types: Optional[Dict[str, ExportType]] = None,
        threshold: float = 0.4,
        follow_pipeline: bool = True,
        background_class: int = 0,
        zone_crop_padding_percent: float = 0.1,
        zone_crop_confidence_threshold: float = 0.7,
        zone_crop_min_coverage_ratio: float = 0.3,
        zone_crop_square_crop: bool = False
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
                    
                    # Run inference
                    result = model.run_inference(
                        image=image,
                        export_type=export_type,
                        threshold=threshold,
                        background_class=background_class
                    )
                    
                    results[task_name] = result
                    print(f"Inference completed for {task_name}")
                    
                except Exception as e:
                    print(f"Error running inference for {task_name}: {e}")
                    results[task_name] = {'error': str(e)}
            
            return results
        else:
            assert 'spatter_segmentation' in self.models or 'spatter_detection' in self.models, "Spatter segmentation or detection model not loaded"
            assert 'zone_segmentation' in self.models, "Zone segmentation model not loaded"
            assert 'spatter_segmentation' in export_types or 'spatter_detection' in export_types, "Spatter segmentation or detection export type not provided"
            assert 'zone_segmentation' in export_types, "Zone segmentation export type not provided"
            
            img_name = os.path.basename(image).split('.')[0]
            key = img_name.split('-')[0]
            print(key, '-----')
            # key = img_name.split(':')[-1].split('-')[0]
            image = Image.open(image).convert('RGB')
            
            # Zone segmentation
            zone_segmentation_result = self.models['zone_segmentation'].run_inference(
                image=image,
                export_type=export_types['zone_segmentation'],
                threshold=threshold,
                background_class=background_class
            )
            results['zone_segmentation'] = zone_segmentation_result['mask']
            zone_predictions = zone_segmentation_result["logits"]
            print(zone_predictions, '-----')
            # Crop based on zone segmentation
            crop_results = crop_zones(
                zone_predictions, 
                [image], 
                [key], 
                self.cropping_config, 
                self.reference_masks, 
                self.models['zone_segmentation'].id2label,
                padding_percent=zone_crop_padding_percent,
                confidence_threshold=zone_crop_confidence_threshold,
                min_coverage_ratio=zone_crop_min_coverage_ratio,
                square_crop=zone_crop_square_crop,
                background_class=background_class
            )
            print(crop_results['all_image_crops'])
            
            
            # Spatter segmentation
            spatter_segmentation_result = self.models['spatter_segmentation'].run_inference(
                image=image,
                export_type=export_types['spatter_segmentation'],
                threshold=threshold
            )
        

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

                # Save raw masks
                if current_export_type == ExportType.MASK and 'mask' in result:
                    mask = np.array(result['mask'])
                    if mask is not None and mask.size > 0:
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
        try:
            # Load original image
            original_image = Image.open(image_path).convert('RGB')
            
            for task_name, result in results.items():
                if 'error' in result:
                    continue
                
                # Determine export type for this task
                export_type = ExportType.BOUNDING_BOX  # Default
                if export_types and task_name in export_types:
                    export_type = export_types[task_name]
                
                # Create visualization based on the specified export type
                if export_type == ExportType.BOUNDING_BOX:
                    # Create bounding box visualization
                    if 'boxes' in result and len(result['boxes']) > 0:
                        vis_image = self.models[task_name].draw_detection_boxes(original_image, result)
                        vis_path = os.path.join(visualizations_folder, f"{image_name}_{task_name}_boxes.jpg")
                        vis_image.save(vis_path)
                        print(f"Saved bounding box visualization: {vis_path}")
                    else:
                        print(f"No bounding boxes found for {task_name}")
                
                elif export_type == ExportType.MASK:
                    # Create mask visualizations
                    if 'mask' in result:
                        mask = result['mask']
                        if mask is not None and mask.size > 0:
                            # Create overlay
                            vis_image = self.models[task_name].create_segmentation_overlay(original_image, mask)
                            vis_path = os.path.join(visualizations_folder, f"{image_name}_{task_name}_mask_overlay.jpg")
                            vis_image.save(vis_path)
                            print(f"Saved mask overlay visualization: {vis_path}")
                            
                            # Also save colored mask only (for visualization)
                            colored_mask = self.models[task_name].generate_colored_mask(mask)
                            mask_image = Image.fromarray(colored_mask)
                            mask_path = os.path.join(visualizations_folder, f"{image_name}_{task_name}_mask_colored.jpg")
                            mask_image.save(mask_path)
                            print(f"Saved colored mask visualization: {mask_path}")
                        else:
                            print(f"No valid mask found for {task_name}")
                    else:
                        print(f"No mask data found for {task_name}")
        
        except Exception as e:
            print(f"Error saving visualizations for {image_name}: {e}")