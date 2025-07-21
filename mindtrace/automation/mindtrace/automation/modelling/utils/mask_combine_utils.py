import torch
import numpy as np
from typing import Dict, List, Tuple, Any
import cv2
import random

def logits_to_mask(logits, conf_threshold, background_class, target_size=None):
    if target_size is not None:
        if logits.ndim == 3:
            logits = logits.unsqueeze(0)
        logits = torch.nn.functional.interpolate(
            logits, size=[target_size[0], target_size[1]], mode="bilinear", align_corners=False
        )
    probs = torch.softmax(logits, dim=1)
    mask_pred = torch.argmax(probs, dim=1)
    # Set low-confidence pixels to background
    if conf_threshold > 0:
        max_probs = torch.max(probs, dim=1)[0]  # Shape: (batch, height, width)
        low_confidence_mask = max_probs < conf_threshold  # Shape: (batch, height, width)
        if mask_pred.shape != low_confidence_mask.shape:
            try:
                low_confidence_mask = low_confidence_mask.view(mask_pred.shape)
            except Exception as e:
                print(f"Error reshaping low_confidence_mask: {e}")
                raise
        mask_pred[low_confidence_mask] = background_class
    return mask_pred

def get_updated_key(key):
    if 'cam' in key.lower():
        return key
    else:
        if key.startswith('c') and key[1:].isdigit():
            return f"cam{key[1:]}"
        else:
            raise ValueError(f"Invalid key: {key}")
            
def crop_zones(
    zone_predictions, 
    imgs,
    keys,
    cropping_config,
    reference_masks,
    zone_segmentation_class_mapping,
    padding_percent=0.1,
    confidence_threshold=0.7,
    min_coverage_ratio=0.3,
    square_crop=False,
    background_class=0
):
    """
    Create individual crops based on zone crop config for batched inference with confidence-based mask combination.
    For each camera, there is a crop config that specifies which area to crop.
    We have pre loaded reference masks for each camera.
    During inference, we get the mask for each camera, and iterate over all the 
        zones that need to be cropped.
    For each zone, we combine prediction and reference masks based on confidence metrics.
    
    Args:
        zone_predictions: Tensor of zone masks [N, 128, 128]
        imgs: List of images [H, W, C]
        keys: List of camera keys
        cropping_config: Cropping config for each camera
        reference_masks: Reference masks for each camera
        zone_segmentation_class_mapping: Mapping of zone segmentation class to index
        padding_percent: Padding around crops (default 10%)
        confidence_threshold: IoU threshold for using prediction vs reference
        min_coverage_ratio: Minimum coverage ratio to accept prediction
        square_crop: If True, return square crops with boundary compensation
        
    Returns:
        dict: Contains all_image_crops, all_mask_crops, crop_metadata, and decision_log
    """
    all_image_crops = []
    all_mask_crops = []
    crop_metadata = {} 
    decision_log = {}
    updated_mask_crops = []
    for i, key in enumerate(keys):
        img = imgs[i]  # Shape: [H, W, C]
        pred_mask = zone_predictions[i]  # Shape: [128, 128]
        combined_mask = torch.zeros(img.shape[:2], dtype=torch.long, device=pred_mask.device)
        image_key = get_updated_key(key)
        
        # Get camera config and reference mask
        cam_config = cropping_config.get(image_key, None) if cropping_config else None
        ref_mask = reference_masks.get(image_key, None) if reference_masks else None
        
        if not cam_config:
            print(f"DEBUG: No cropping config found for {image_key}")
            continue
        # Resize masks to image dimensions
        img_h, img_w = img.shape[:2]
        print(pred_mask, 'pred_mask')
        pred_mask_resized = logits_to_mask(
            pred_mask, 
            confidence_threshold, 
            background_class, 
            target_size=(img_h, img_w)
        ).view(img_h, img_w)
        print(pred_mask_resized, 'pred_mask_resized')
        # ref_mask_resized = None
        if ref_mask is not None:
            ref_mask = torch.nn.functional.interpolate(
                ref_mask.unsqueeze(0).unsqueeze(0).float(), 
                size=(img_h, img_w), 
                mode='nearest'
            ).squeeze().long()
        
        # Initialize metadata for this image
        crop_metadata[image_key] = []
        decision_log[image_key] = []
        
        # Process each crop configuration
        for crop_idx, crop_name in enumerate(cam_config.keys()):
            zone_ids = cam_config[crop_name]
            zone_indices = [int(zone_segmentation_class_mapping[str(c)]) for c in zone_ids]
            
            # ref_mask = torch.nn.functional.interpolate(
            #     ref_mask.unsqueeze(0).unsqueeze(0).float(), 
            #     size=(pred_mask_resized.shape[0], pred_mask_resized.shape[1]), 
            #     mode='nearest'
            # ).squeeze().long()
            # Create combined mask for this crop using confidence-based approach
            combined_crop_mask, crop_decisions = _create_confidence_based_crop_mask(
                pred_mask_resized, ref_mask, zone_indices, 
                confidence_threshold, min_coverage_ratio
            )
            # Combine masks preserving class IDs (non-zero values from combined_crop_mask overwrite combined_mask)
            combined_mask[combined_crop_mask > 0] = combined_crop_mask[combined_crop_mask > 0]
            # Store decision log
            decision_log[image_key].append({
                'crop_name': crop_name,
                'zone_ids': zone_ids,
                'decisions': crop_decisions
            })
            print(combined_crop_mask, 'combined_crop_mask')
            if combined_crop_mask.sum() == 0:
                print(f"WARNING: Empty mask for crop {crop_name}")
                continue
            
            # Get bounding box with padding (and optionally square)
            # Convert class mask to boolean mask for bbox calculation
            bbox_mask = combined_crop_mask > 0
            crop_bbox = _get_padded_bbox(bbox_mask, padding_percent, img_h, img_w, square_crop)
            print(crop_bbox, 'crop_bbox')
            # Extract crop from image and mask
            y1, y2, x1, x2 = crop_bbox
            image_crop = img[y1:y2, x1:x2]
            mask_crop = combined_crop_mask[y1:y2, x1:x2]
            
            # Store crops and metadata
            all_image_crops.append(image_crop)
            all_mask_crops.append(mask_crop)
            updated_mask_crops.append(combined_mask)

            crop_metadata[image_key].append({
                'crop_name': crop_name,
                'zone_ids': zone_ids,
                'bbox': crop_bbox,  # (y1, y2, x1, x2) in original image coordinates
                'crop_index': len(all_image_crops) - 1,  # Index in the flat crop list
                'original_img_shape': (img_h, img_w),
                'crop_shape': image_crop.shape[:2]
            })
            print(crop_metadata, 'crop_metadata')
            
    return {
        'all_image_crops': all_image_crops,
        'all_mask_crops': all_mask_crops,
        'crop_metadata': crop_metadata,
        'decision_log': decision_log,
        'updated_mask_crops': updated_mask_crops
    }

def _create_confidence_based_crop_mask(pred_mask, ref_mask, zone_indices, 
                                     confidence_threshold=0.7, min_coverage_ratio=0.3):
    """
    Create a combined crop mask using confidence-based approach for multiple zones.
    
    Args:
        pred_mask: Predicted mask tensor [H, W]
        ref_mask: Reference mask tensor [H, W] (can be None)
        zone_indices: List of zone indices to include in this crop
        confidence_threshold: IoU threshold for using prediction
        min_coverage_ratio: Minimum coverage ratio to accept prediction
    
    Returns:
        combined_mask: Class mask tensor [H, W] with zone class IDs preserved
        decisions: Dict with decision info for each zone
    """
    combined_mask = torch.zeros_like(pred_mask, dtype=pred_mask.dtype)
    decisions = {}
    for zone_idx in zone_indices:
        # Get masks for this specific zone
        pred_zone = (pred_mask == zone_idx)
        
        if ref_mask is not None:
            ref_zone = (ref_mask == zone_idx)
        else:
            ref_zone = None
        # Apply confidence-based decision
        chosen_mask, decision = _combine_masks_with_confidence(
            pred_zone, ref_zone, zone_idx, confidence_threshold, min_coverage_ratio
        )
        # Add to combined mask with the correct zone class ID
        combined_mask[chosen_mask] = zone_idx
        decisions[zone_idx] = decision
    
    return combined_mask, decisions

def _combine_masks_with_confidence(pred_zone, ref_zone, zone_id, 
                                 confidence_threshold=0.7, min_coverage_ratio=0.3):
    """
    Combine predicted and reference masks for a single zone based on confidence metrics.
    
    Args:
        pred_zone: Boolean tensor for predicted zone
        ref_zone: Boolean tensor for reference zone (can be None)
        zone_id: Zone identifier for logging
        confidence_threshold: IoU threshold
        min_coverage_ratio: Minimum coverage ratio
    
    Returns:
        chosen_mask: Boolean tensor
        decision: String describing the decision made
    """
    
    # Case 1: No reference mask available - use prediction
    if ref_zone is None:
        if pred_zone.sum() > 0:
            return pred_zone, f"prediction_only_available"
        else:
            return torch.zeros_like(pred_zone, dtype=torch.bool), f"no_mask_available"
    
    # Case 2: No prediction for this zone - use reference
    if pred_zone.sum() == 0:
        return ref_zone, f"reference_fallback_no_prediction"
    
    # Case 3: No reference for this zone - use prediction
    if ref_zone.sum() == 0:
        return pred_zone, f"prediction_no_reference"
    
    # Case 4: Both available - calculate confidence metrics
    intersection = (pred_zone & ref_zone).sum().float()
    union = (pred_zone | ref_zone).sum().float()
    iou = intersection / union if union > 0 else 0.0
    
    pred_area = pred_zone.sum().float()
    ref_area = ref_zone.sum().float()
    coverage_ratio = pred_area / ref_area
    area_ratio = min(pred_area, ref_area) / max(pred_area, ref_area)  # Always between 0 and 1
    
    # Enhanced decision logic with area check
    # Good prediction: reasonable IoU OR (good area ratio AND decent coverage)
    area_is_reasonable = area_ratio > 0.5  # Areas are within 2x of each other
    coverage_is_acceptable = min_coverage_ratio < coverage_ratio < (1/min_coverage_ratio)
    
    if iou > confidence_threshold and coverage_is_acceptable:
        # High IoU and good coverage - use prediction
        return pred_zone, f"prediction_confident_iou_{iou:.3f}_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif area_is_reasonable and coverage_is_acceptable and iou > (confidence_threshold * 0.5):
        # Lower IoU but good area match - might be shifted but correct
        return pred_zone, f"prediction_area_match_iou_{iou:.3f}_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif coverage_ratio < min_coverage_ratio:
        # Severely under-segmented
        return ref_zone, f"reference_undersegmented_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif coverage_ratio > (1/min_coverage_ratio):
        # Over-segmented
        return ref_zone, f"reference_oversegmented_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif not area_is_reasonable:
        # Area is very different - likely wrong prediction
        return ref_zone, f"reference_bad_area_ratio_{area_ratio:.3f}_iou_{iou:.3f}"
    
    else:
        # Low IoU, might be shifted
        return ref_zone, f"reference_low_iou_{iou:.3f}_area_{area_ratio:.3f}"

def _get_padded_bbox(mask, padding_percent, img_h, img_w, square_crop=False):
    """
    Get bounding box around mask with padding.
    
    Args:
        mask: Boolean tensor [H, W]
        padding_percent: Padding as percentage of bbox size
        img_h, img_w: Image dimensions for clipping
        square_crop: If True, return a square crop. If the square goes out of bounds,
                    take pixels from the opposite side to compensate.
    
    Returns:
        tuple: (y1, y2, x1, x2) coordinates
    """
    if mask.sum() == 0:
        return (0, img_h, 0, img_w)
    
    # Find bounding box
    rows = torch.any(mask, dim=1)
    cols = torch.any(mask, dim=0)
    
    non_zero_coords = torch.nonzero(mask)
    if len(non_zero_coords) == 0:
        return (0, img_h, 0, img_w)
    
    min_y, max_y = non_zero_coords[:, 0].min(), non_zero_coords[:, 0].max()
    min_x, max_x = non_zero_coords[:, 1].min(), non_zero_coords[:, 1].max()
    
    min_y, max_y, min_x, max_x = min_y.item(), max_y.item(), min_x.item(), max_x.item()
    
    # Add padding
    h_padding = int((max_y - min_y) * padding_percent)
    w_padding = int((max_x - min_x) * padding_percent)
    
    y1 = max(0, min_y - h_padding)
    y2 = min(img_h, max_y + h_padding)
    x1 = max(0, min_x - w_padding)
    x2 = min(img_w, max_x + w_padding)
    
    if not square_crop:
        return (y1, y2, x1, x2)
    
    # Square crop logic
    # Calculate current dimensions
    current_height = y2 - y1
    current_width = x2 - x1
    
    # Use the larger dimension to create a square
    side_length = max(current_height, current_width)
    
    # Calculate center of current bbox
    center_y = (y1 + y2) // 2
    center_x = (x1 + x2) // 2
    
    # Calculate half side length
    half_side = side_length // 2
    
    # Initial square coordinates
    square_y1 = center_y - half_side
    square_y2 = center_y + half_side
    square_x1 = center_x - half_side
    square_x2 = center_x + half_side
    
    # Adjust if square goes out of bounds
    # Vertical adjustment
    if square_y1 < 0:
        # Shift down to fit within bounds
        shift = -square_y1
        square_y1 = 0
        square_y2 = min(img_h, square_y2 + shift)
    elif square_y2 > img_h:
        # Shift up to fit within bounds
        shift = square_y2 - img_h
        square_y2 = img_h
        square_y1 = max(0, square_y1 - shift)
    
    # Horizontal adjustment
    if square_x1 < 0:
        # Shift right to fit within bounds
        shift = -square_x1
        square_x1 = 0
        square_x2 = min(img_w, square_x2 + shift)
    elif square_x2 > img_w:
        # Shift left to fit within bounds
        shift = square_x2 - img_w
        square_x2 = img_w
        square_x1 = max(0, square_x1 - shift)
    
    # Final adjustment to ensure we have the largest possible square
    # if the image is smaller than our desired side_length
    final_height = square_y2 - square_y1
    final_width = square_x2 - square_x1
    final_side = min(final_height, final_width)
    
    # Re-center the final square
    center_y = (square_y1 + square_y2) // 2
    center_x = (square_x1 + square_x2) // 2
    half_final_side = final_side // 2
    
    final_y1 = center_y - half_final_side
    final_y2 = center_y + half_final_side
    final_x1 = center_x - half_final_side
    final_x2 = center_x + half_final_side
    
    return (final_y1, final_y2, final_x1, final_x2)

def reconstruct_crops_to_full_image(crop_results, crop_metadata, original_img_shape):
    """
    Reconstruct crop results back to full image coordinates.
    
    Args:
        crop_results: Results from processing individual crops
        crop_metadata: Metadata dict from crop_zones function
        original_img_shape: (H, W) of original image
    
    Returns:
        dict: Results mapped back to full image coordinates per camera
    """
    reconstructed = {}
    
    for image_key, metadata_list in crop_metadata.items():
        reconstructed[image_key] = []
        
        for metadata in metadata_list:
            crop_idx = metadata['crop_index']
            y1, y2, x1, x2 = metadata['bbox']
            
            # Get results for this crop
            if crop_idx < len(crop_results):
                crop_result = crop_results[crop_idx]
                
                # Transform coordinates back to full image space
                # (This depends on what your crop_result contains)
                transformed_result = {
                    'crop_name': metadata['crop_name'],
                    'zone_ids': metadata['zone_ids'],
                    'bbox_in_original': (y1, y2, x1, x2),
                    'crop_result': crop_result,
                    # Add coordinate transformation here based on your specific results
                }
                
                reconstructed[image_key].append(transformed_result)
    
    return reconstructed

def combine_crops(zone_crops, spatter_crops, crop_metadata, original_img_shapes, 
                 zone_classes=22, spatter_classes=2, overlap_strategy='max', conf_threshold=0.0,
                 background_class=0):
    """
    Combine cropped masks back into full-sized images and merge zone + spatter segmentation.
    
    Args:
        zone_crops: List of zone segmentation crops [N_crops, H_crop, W_crop]
        spatter_crops: List of spatter segmentation crops [N_crops, H_crop, W_crop] 
        crop_metadata: Metadata dict containing bbox info for each crop
        original_img_shapes: List of (H, W) for each original image, or single (H, W) if all same
        zone_classes: Number of zone segmentation classes (default 22)
        spatter_classes: Number of spatter segmentation classes (default 2) 
        overlap_strategy: How to handle overlapping crops ('max', 'last', 'weighted')
    
    Returns:
        dict: {
            'zone_masks': {camera_key: reconstructed_zone_mask},
            'spatter_masks': {camera_key: reconstructed_spatter_mask}, 
            'combined_masks': {camera_key: combined_zone_and_spatter_mask}
        }
    """
    
    # Handle different input formats for original_img_shapes
    if isinstance(original_img_shapes, dict):
        # Dictionary mapping camera keys to shapes
        img_shapes = original_img_shapes
    elif isinstance(original_img_shapes, tuple):
        # Single shape provided - use for all images
        img_shapes = {cam: original_img_shapes for cam in crop_metadata.keys()}
    elif isinstance(original_img_shapes, list):
        # Assume order matches crop_metadata keys
        cam_keys = list(crop_metadata.keys())
        img_shapes = {cam_keys[i]: original_img_shapes[i] for i in range(len(cam_keys))}
    else:
        raise ValueError("original_img_shapes must be dict, tuple (H, W) or list of tuples")
    
    zone_masks = {}
    spatter_masks = {}
    combined_masks = {}
    
    # Process each camera
    for camera_key, metadata_list in crop_metadata.items():
        img_h, img_w = img_shapes[camera_key]
        
        # Initialize empty masks
        zone_mask = torch.zeros((img_h, img_w), dtype=torch.long, device=zone_crops[0].device)
        spatter_mask = torch.zeros((img_h, img_w), dtype=torch.long, device=spatter_crops[0].device)
        
        # For weighted overlap strategy
        if overlap_strategy == 'weighted':
            zone_weights = torch.zeros((img_h, img_w), dtype=torch.float, device=zone_crops[0].device)
            spatter_weights = torch.zeros((img_h, img_w), dtype=torch.float, device=spatter_crops[0].device)
            zone_accumulator = torch.zeros((img_h, img_w), dtype=torch.float, device=zone_crops[0].device)
            spatter_accumulator = torch.zeros((img_h, img_w), dtype=torch.float, device=spatter_crops[0].device)

        # Process each crop for this camera
        for metadata in metadata_list:
            crop_idx = metadata['crop_index']
            y1, y2, x1, x2 = metadata['bbox']
            
            # Get the crops
            zone_crop = zone_crops[crop_idx]  # Shape: [H_crop, W_crop] - already the right size
            spatter_crop = spatter_crops[crop_idx]  # Shape: [H_model, W_model] - model output size
            
            # Ensure crops are torch tensors
            if not isinstance(zone_crop, torch.Tensor):
                zone_crop = torch.tensor(zone_crop)
            if not isinstance(spatter_crop, torch.Tensor):
                spatter_crop = torch.tensor(spatter_crop)

            # The zone_crop should already be the right size for the bbox
            # The spatter_crop needs to be resized to match the zone_crop size
            expected_h, expected_w = y2 - y1, x2 - x1
            zone_h, zone_w = zone_crop.shape[-2:]
            spatter_h, spatter_w = spatter_crop.shape[-2:]

            # # Ensure zone_crop is resized if needed
            # if (zone_h, zone_w) != (expected_h, expected_w):
                # zone_crop = torch.nn.functional.interpolate(
                #     zone_crop.unsqueeze(0).unsqueeze(0).float(),
                #     size=(expected_h, expected_w),
                #     mode='nearest'
                # ).squeeze().long()

            spatter_crop = logits_to_mask(
                spatter_crop, 
                conf_threshold=conf_threshold, 
                background_class=background_class,
                target_size=(expected_h, expected_w)
            )
            
            # Handle different overlap strategies
            if overlap_strategy == 'max':
                # Take maximum value (higher class number wins)
                current_zone = zone_mask[y1:y2, x1:x2]
                current_spatter = spatter_mask[y1:y2, x1:x2]
                
                zone_mask[y1:y2, x1:x2] = torch.maximum(current_zone, zone_crop)
                spatter_mask[y1:y2, x1:x2] = torch.maximum(current_spatter, spatter_crop)
                
            elif overlap_strategy == 'last':
                # Last write wins (simple overwrite)
                zone_mask[y1:y2, x1:x2] = zone_crop
                spatter_mask[y1:y2, x1:x2] = spatter_crop
                
            elif overlap_strategy == 'weighted':
                # Weight by distance from crop center (closer to center = higher weight)
                crop_center_y = (y1 + y2) // 2
                crop_center_x = (x1 + x2) // 2
                
                # Create weight map (higher weight near center)
                y_coords, x_coords = torch.meshgrid(
                    torch.arange(y1, y2, dtype=torch.float),
                    torch.arange(x1, x2, dtype=torch.float),
                    indexing='ij'
                )
                
                # Distance from center (normalized)
                max_dist = max(expected_h, expected_w) / 2
                distances = torch.sqrt((y_coords - crop_center_y)**2 + (x_coords - crop_center_x)**2)
                weights = torch.clamp(1.0 - distances / max_dist, min=0.1)  # Min weight 0.1
                
                # Accumulate weighted values
                zone_accumulator[y1:y2, x1:x2] += zone_crop.float() * weights
                spatter_accumulator[y1:y2, x1:x2] += spatter_crop.float() * weights
                zone_weights[y1:y2, x1:x2] += weights
                spatter_weights[y1:y2, x1:x2] += weights
            
            else:
                raise ValueError(f"Unknown overlap_strategy: {overlap_strategy}")
        
        # Finalize weighted strategy
        if overlap_strategy == 'weighted':
            # Avoid division by zero
            zone_weights = torch.clamp(zone_weights, min=1e-6)
            spatter_weights = torch.clamp(spatter_weights, min=1e-6)
            
            zone_mask = (zone_accumulator / zone_weights).round().long()
            spatter_mask = (spatter_accumulator / spatter_weights).round().long()
        
        # Store individual masks
        zone_masks[camera_key] = zone_mask
        spatter_masks[camera_key] = spatter_mask
        


        # Combine zone and spatter masks
        # Strategy: Add spatter classes to zone mask with offset
        # Zone classes: 0 to zone_classes-1
        # Spatter classes: zone_classes to zone_classes+spatter_classes-1
        combined_mask = zone_mask.clone()
        combined_mask[spatter_mask > 0] = zone_classes + 1
        combined_masks[camera_key] = combined_mask
    
    return {
        'zone_masks': zone_masks,
        'spatter_masks': spatter_masks, 
        'combined_masks': combined_masks
    }

def create_mask_overlay(image, zone_mask, spatter_mask, alpha=0.5):
    """
    Create an overlay visualization combining zone and spatter masks on original image.
    Spatter is drawn on top of zones.
    
    Args:
        image: Original image as numpy array [H, W, C] 
        zone_mask: Zone segmentation mask as torch tensor [H, W] with classes 1-22
        spatter_mask: Spatter mask as torch tensor [H, W] with binary values 0,1
        alpha: Transparency factor (0.0 = transparent, 1.0 = opaque)
    
    Returns:
        numpy array: RGB image with colored mask overlay
    """
    # Ensure image is numpy array
    if isinstance(image, torch.Tensor):
        image = image.cpu().numpy()
    
    # Ensure masks are numpy arrays
    if isinstance(zone_mask, torch.Tensor):
        zone_mask = zone_mask.cpu().numpy()
    if isinstance(spatter_mask, torch.Tensor):
        spatter_mask = spatter_mask.cpu().numpy()
    
    # Ensure image is uint8
    if image.dtype != np.uint8:
        if image.max() <= 1.0:
            image = (image * 255).astype(np.uint8)
        else:
            image = image.astype(np.uint8)
    
    # Create a copy of the original image
    overlay = image.copy()
    
    # Get global fixed color map
    colors = get_global_color_map()
    
    # Create colored overlay
    colored_mask = np.zeros_like(image)
    
    # First, apply zone colors
    unique_zones = np.unique(zone_mask)
    unique_zones = unique_zones[unique_zones > 0]  # Remove background
    
    for zone_id in unique_zones:
        if zone_id in colors:
            # Create binary mask for this zone
            zone_pixels = (zone_mask == zone_id)
            
            # Apply color to this zone
            for c in range(3):  # RGB channels
                colored_mask[:, :, c][zone_pixels] = colors[zone_id][c]
    
    # Then, overlay spatter on top (spatter wins where it exists)
    spatter_pixels = (spatter_mask == 1)
    if spatter_pixels.sum() > 0:
        # Use class 22 color for spatter (bright red)
        spatter_color = colors.get(22, [255, 0, 0])  # Default to red if not found
        for c in range(3):  # RGB channels
            colored_mask[:, :, c][spatter_pixels] = spatter_color[c]
    
    # Blend original image with colored mask
    result = cv2.addWeighted(overlay, 1-alpha, colored_mask, alpha, 0)
    
    return result

def get_global_color_map():
    """
    Get the global fixed color map for all classes.
    Classes 1-25: Fixed zone colors
    Classes 26+: Fixed spatter colors (bright red, orange) then random colors
    """
    colors = {0: (0, 0, 0)}  # Background is black
    
    # Fixed color palette for zone classes 1-25
    fixed_zone_colors = [
        (255, 0, 0),     # Red
        (0, 255, 0),     # Green  
        (0, 0, 255),     # Blue
        (255, 255, 0),   # Yellow
        (255, 0, 255),   # Magenta
        (0, 255, 255),   # Cyan
        (255, 165, 0),   # Orange
        (128, 0, 128),   # Purple
        (255, 192, 203), # Pink
        (0, 128, 0),     # Dark Green
        (0, 0, 128),     # Navy
        (128, 128, 0),   # Olive
        (128, 0, 0),     # Maroon
        (0, 128, 128),   # Teal
        (255, 20, 147),  # Deep Pink
        (50, 205, 50),   # Lime Green
        (255, 69, 0),    # Red Orange
        (138, 43, 226),  # Blue Violet
        (0, 191, 255),   # Deep Sky Blue
        (255, 215, 0),   # Gold
        (220, 20, 60),   # Crimson
        (124, 252, 0),   # Lawn Green
        (30, 144, 255),  # Dodger Blue
        (255, 105, 180), # Hot Pink
        (34, 139, 34),   # Forest Green
    ]
    
    # Assign fixed zone colors for classes 1-25
    for i in range(1, 26):
        colors[i] = fixed_zone_colors[i-1]
    
    # Fixed spatter colors for classes starting from zone classes
    # Assuming spatter starts from class 22 (zone_classes)
    spatter_colors = [
        (255, 50, 50),   # Bright Red for spatter class 1
        (255, 165, 0),   # Orange for spatter class 2  
    ]
    
    # Add spatter colors
    for i, color in enumerate(spatter_colors):
        colors[22 + i] = color  # Classes 22, 23 for spatter
    
    # For any additional classes beyond what we've defined, use random colors
    random.seed(42)  # For reproducibility
    for i in range(26, 100):  # Predefine up to 100 classes
        if i not in colors:
            colors[i] = (
                random.randint(50, 255),
                random.randint(50, 255),
                random.randint(50, 255)
            )
    
    return colors

def create_filtered_zone_spatter_results(zone_masks, spatter_masks, zone_class_mapping, background_class=0):
    """
    Filter spatter masks to only include spatter within zone masks and create results
    in the exact format matching the API response template.
    
    Args:
        zone_masks: Dict of {camera_key: zone_mask_tensor} with zone classes 1-22
        spatter_masks: Dict of {camera_key: spatter_mask_tensor} with binary values 0,1
        zone_class_mapping: Dict mapping zone names to class IDs (e.g., {"OB_Z1": "1", "OB_Z2": "2"})
    
    Returns:
        Dict with structure matching API template:
        {
            camera_key: {
                "OB_Z1": {
                    "class": "Healthy" or "Defective", 
                    "box": [[xc, yc, w, h], ...]  # Zone box + spatter boxes if any
                }
            }
        }
    """
    # Create reverse mapping from class ID to zone name
    id_to_zone_name = {}
    for zone_name, class_id in zone_class_mapping.items():
        id_to_zone_name[int(class_id)] = zone_name
    
    results = {}
    
    for camera_key in zone_masks.keys():
        zone_mask = zone_masks[camera_key]
        spatter_mask = spatter_masks[camera_key]

        # Filter spatter to only include spatter within zones
        zone_regions = zone_mask > 0  # Any zone (non-background)
        filtered_spatter = spatter_mask.clone()
        filtered_spatter[~zone_regions] = 0  # Remove spatter outside zones
        
        # Find unique zones present
        unique_zones = zone_mask.unique()
        zones_present = unique_zones[unique_zones > 0].tolist()  # Remove background
        
        # Initialize camera results in API format
        camera_results = {}
        
        # Process each zone individually
        for zone_id in zones_present:
            # Get the actual zone name from mapping
            if zone_id not in id_to_zone_name:
                print(f"WARNING: Zone ID {zone_id} not found in class mapping")
                continue
                
            zone_name = id_to_zone_name[zone_id]
            
            # Create mask for this specific zone
            zone_specific_mask = (zone_mask == zone_id)
            
            # Get spatter within this zone only
            zone_spatter = filtered_spatter.clone()
            zone_spatter[~zone_specific_mask] = 0
            
            # Calculate if zone has spatter
            spatter_pixel_count = int(zone_spatter.sum())
            has_spatter = spatter_pixel_count > 0
            
            # Determine class based on spatter presence
            zone_class = "Defective" if has_spatter else "Healthy"
            
            # Calculate zone bounding box [xc, yc, w, h]
            zone_bbox = _get_bbox_from_mask(zone_specific_mask)
                        
            # Add spatter bounding boxes if present
            if has_spatter:
                spatter_bboxes = _get_spatter_bboxes(zone_spatter)
            else:
                spatter_bboxes = []
            
            # Store in API format using actual zone name
            camera_results[zone_name] = {
                "class": zone_class,
                "box": zone_bbox,
                "spatter_box": spatter_bboxes
            }
        
        results[camera_key] = camera_results
    
    return results

def _get_bbox_from_mask(mask):
    """
    Get bounding box from binary mask in [xc, yc, w, h] format.
    
    Args:
        mask: Binary numpy array [H, W]
    
    Returns:
        list: [xc, yc, w, h] where xc, yc are center coordinates
    """
    if mask.sum() == 0:
        return [0, 0, 0, 0]
    
    # Find bounding box coordinates
    rows = torch.any(mask, axis=1)
    cols = torch.any(mask, axis=0)
    
    if not rows.any() or not cols.any():
        return [0, 0, 0, 0]
    
    y_indices = torch.where(rows)[0]
    x_indices = torch.where(cols)[0]
    
    y_min, y_max = y_indices[0], y_indices[-1]
    x_min, x_max = x_indices[0], x_indices[-1]
    
    # Calculate center coordinates and dimensions
    w = int(x_max - x_min + 1)
    h = int(y_max - y_min + 1)
    xc = int(x_min + w // 2)
    yc = int(y_min + h // 2)
    # return [xc, yc, w, h]
    return [int(x_min), int(y_min), int(w), int(h)]

def _get_spatter_bboxes(spatter_mask):
    """
    Get bounding boxes for connected components of spatter in [xc, yc, w, h] format.
    
    Args:
        spatter_mask: Binary numpy array [H, W] with spatter pixels
    
    Returns:
        list: List of [xc, yc, w, h] bounding boxes for each spatter region
    """
    if spatter_mask.sum() == 0:
        return []
    
    # Find connected components
    from scipy import ndimage
    labeled_mask, num_features = ndimage.label(spatter_mask.cpu().numpy())
    
    spatter_bboxes = []
    for i in range(1, num_features + 1):
        component_mask = (labeled_mask == i)
        bbox = _get_bbox_from_mask(torch.from_numpy(component_mask))
        if bbox != [0, 0, 0, 0]:  # Valid bounding box
            spatter_bboxes.append(bbox)
    
    return spatter_bboxes