import torch
import numpy as np
from typing import Dict, List, Tuple, Any
import cv2
import random
import os

def get_updated_key(key):
    if 'cam' in key.lower():
        return key
    else:
        if key.startswith('c') and key[1:].isdigit():
            return f"cam{key[1:]}"
        else:
            raise ValueError(f"Invalid key: {key}")

def crop_zones(
    zone_masks: List[torch.Tensor],
    imgs: List[np.ndarray],
    keys: List[str],
    cropping_config: Dict,
    reference_masks: Dict,
    zone_segmentation_class_mapping: Dict,
    padding_percent: float = 0.1,
    confidence_threshold: float = 0.7,
    min_coverage_ratio: float = 0.3,
    square_crop: bool = False,
    background_class: int = 0,
    image_names: List[str] = None,
    spatter_masks: List[np.ndarray] = None
) -> Dict:
    """
    Create individual crops based on zone crop config for batched inference with confidence-based mask combination.
    For each camera, there is a crop config that specifies which area to crop.
    We have pre loaded reference masks for each camera.
    During inference, we get the mask for each camera, and iterate over all the 
        zones that need to be cropped.
    For each zone, we combine prediction and reference masks based on confidence metrics.
    
    Args:
        zone_masks: List of zone mask tensors [H, W]
        imgs: List of images [H, W, C]
        keys: List of camera keys
        cropping_config: Cropping config for each camera
        reference_masks: Reference masks for each camera
        zone_segmentation_class_mapping: Mapping of zone segmentation class to index
        padding_percent: Padding around crops (default 10%)
        confidence_threshold: IoU threshold for using prediction vs reference
        min_coverage_ratio: Minimum coverage ratio to accept prediction
        square_crop: If True, return square crops with boundary compensation
        image_names: List of image names for debugging purposes.
        spatter_masks: List of spatter masks corresponding to the images.
        
    Returns:
        dict: Contains all_image_crops, all_mask_crops, all_spatter_mask_crops, crop_metadata, and decision_log
    """
    viz_dir = "viz"
    if image_names and not os.path.exists(viz_dir):
        os.makedirs(viz_dir)

    all_image_crops = []
    all_mask_crops = []
    all_spatter_mask_crops = []
    crop_metadata = {} 
    decision_log = {}

    for i, key in enumerate(keys):
        img = imgs[i]
        pred_mask_resized = zone_masks[i]
        spatter_mask = spatter_masks[i] if spatter_masks is not None and i < len(spatter_masks) else None
        combined_mask = torch.zeros(img.shape[:2], dtype=torch.long, device=pred_mask_resized.device)
        image_key = get_updated_key(key)
        image_name_for_debug = image_names[i] if image_names else f"image_{i}"
        
        cam_config = cropping_config.get(image_key, None) if cropping_config else None
        ref_mask = reference_masks.get(image_key, None) if reference_masks else None
        
        if not cam_config:
            print(f"DEBUG: No cropping config found for {image_key}")
            continue

        img_h, img_w = img.shape[:2]
        
        if ref_mask is not None:
            ref_mask = torch.nn.functional.interpolate(
                ref_mask.unsqueeze(0).unsqueeze(0).float(), 
                size=(img_h, img_w), 
                mode='nearest'
            ).squeeze().long()
        
        crop_metadata[image_key] = []
        decision_log[image_key] = []
        
        for crop_idx, crop_name in enumerate(cam_config.keys()):
            zone_ids = cam_config[crop_name]
            zone_indices = [int(zone_segmentation_class_mapping[c]) for c in zone_ids]
            
            combined_crop_mask, crop_decisions = _create_confidence_based_crop_mask(
                pred_mask_resized, ref_mask, zone_indices, 
                confidence_threshold, min_coverage_ratio
            )
            combined_mask[combined_crop_mask > 0] = combined_crop_mask[combined_crop_mask > 0]
            decision_log[image_key].append({
                'crop_name': crop_name,
                'zone_ids': zone_ids,
                'decisions': crop_decisions
            })
            
            if combined_crop_mask.sum() == 0:
                print(f"WARNING: Empty mask for crop {crop_name} in {image_name_for_debug}")
                continue
            
            print(f"INFO: Non-empty crop generated for {image_name_for_debug}, crop: {crop_name}")

            bbox_mask = combined_crop_mask > 0
            crop_bbox = _get_padded_bbox(bbox_mask, padding_percent, img_h, img_w, square_crop)
            
            y1, y2, x1, x2 = crop_bbox
            image_crop = img[y1:y2, x1:x2]
            mask_crop = combined_crop_mask[y1:y2, x1:x2]
            
            spatter_crop = None
            if spatter_mask is not None:
                spatter_crop = spatter_mask[y1:y2, x1:x2]
            
            if image_names and spatter_crop is not None and np.any(spatter_crop):
                # Create color mask for visualization
                color_mask = np.zeros_like(image_crop)
                mask_crop_np = mask_crop.cpu().numpy()
                
                # Create a color map for the zones in this crop
                colors = {zone_idx: (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)) 
                          for zone_idx in zone_indices}

                for zone_idx in zone_indices:
                    if zone_idx in colors:
                        color_mask[mask_crop_np == zone_idx] = colors[zone_idx]

                # Blend image and mask
                overlayed_image = cv2.addWeighted(image_crop, 0.7, color_mask, 0.3, 0)
                
                # Save the overlay image
                save_path = os.path.join(viz_dir, f"{image_name_for_debug}_{crop_name}_overlay.jpg")
                cv2.imwrite(save_path, cv2.cvtColor(overlayed_image, cv2.COLOR_RGB2BGR))
                
                # Save the non-empty spatter mask to viz folder, scaling it for visibility
                spatter_mask_save_path = os.path.join(viz_dir, f"{image_name_for_debug}_{crop_name}_spatter_mask.png")
                cv2.imwrite(spatter_mask_save_path, (spatter_crop > 0).astype(np.uint8) * 255)

            all_image_crops.append(image_crop)
            all_mask_crops.append(mask_crop)
            all_spatter_mask_crops.append(spatter_crop)

            crop_metadata[image_key].append({
                'crop_name': crop_name,
                'zone_ids': zone_ids,
                'bbox': crop_bbox,
                'crop_index': len(all_image_crops) - 1,
                'original_img_shape': (img_h, img_w),
                'crop_shape': image_crop.shape[:2]
            })
            
    return {
        'all_image_crops': all_image_crops,
        'all_mask_crops': all_mask_crops,
        'all_spatter_mask_crops': all_spatter_mask_crops,
        'crop_metadata': crop_metadata,
        'decision_log': decision_log,
    }

def _create_confidence_based_crop_mask(pred_mask, ref_mask, zone_indices, 
                                     confidence_threshold=0.7, min_coverage_ratio=0.3):
    combined_mask = torch.zeros_like(pred_mask, dtype=torch.long)
    decisions = {}
    for zone_idx in zone_indices:
        pred_zone = (pred_mask == zone_idx)
        
        if ref_mask is not None:
            ref_zone = (ref_mask == zone_idx)
        else:
            ref_zone = None
        chosen_mask, decision = _combine_masks_with_confidence(
            pred_zone, ref_zone, zone_idx, confidence_threshold, min_coverage_ratio
        )
        combined_mask[chosen_mask] = zone_idx
        decisions[zone_idx] = decision
    
    return combined_mask, decisions

def _combine_masks_with_confidence(pred_zone, ref_zone, zone_id, 
                                 confidence_threshold=0.7, min_coverage_ratio=0.3):
    if ref_zone is None:
        if pred_zone.sum() > 0:
            return pred_zone, f"prediction_only_available"
        else:
            return torch.zeros_like(pred_zone, dtype=torch.bool), f"no_mask_available"
    
    if pred_zone.sum() == 0:
        return ref_zone, f"reference_fallback_no_prediction"
    
    if ref_zone.sum() == 0:
        return pred_zone, f"prediction_no_reference"
    
    intersection = (pred_zone & ref_zone).sum().float()
    union = (pred_zone | ref_zone).sum().float()
    iou = intersection / union if union > 0 else 0.0
    
    pred_area = pred_zone.sum().float()
    ref_area = ref_zone.sum().float()
    coverage_ratio = pred_area / ref_area
    area_ratio = min(pred_area, ref_area) / max(pred_area, ref_area)
    
    area_is_reasonable = area_ratio > 0.5
    coverage_is_acceptable = min_coverage_ratio < coverage_ratio < (1/min_coverage_ratio)
    
    if iou > confidence_threshold and coverage_is_acceptable:
        return pred_zone, f"prediction_confident_iou_{iou:.3f}_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif area_is_reasonable and coverage_is_acceptable and iou > (confidence_threshold * 0.5):
        return pred_zone, f"prediction_area_match_iou_{iou:.3f}_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif coverage_ratio < min_coverage_ratio:
        return ref_zone, f"reference_undersegmented_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif coverage_ratio > (1/min_coverage_ratio):
        return ref_zone, f"reference_oversegmented_cov_{coverage_ratio:.3f}_area_{area_ratio:.3f}"
    
    elif not area_is_reasonable:
        return ref_zone, f"reference_bad_area_ratio_{area_ratio:.3f}_iou_{iou:.3f}"
    
    else:
        return ref_zone, f"reference_low_iou_{iou:.3f}_area_{area_ratio:.3f}"

def _get_padded_bbox(mask, padding_percent, img_h, img_w, square_crop=False):
    if mask.sum() == 0:
        return (0, img_h, 0, img_w)
    
    non_zero_coords = torch.nonzero(mask)
    if len(non_zero_coords) == 0:
        return (0, img_h, 0, img_w)
    
    min_y, max_y = non_zero_coords[:, 0].min(), non_zero_coords[:, 0].max()
    min_x, max_x = non_zero_coords[:, 1].min(), non_zero_coords[:, 1].max()
    
    min_y, max_y, min_x, max_x = min_y.item(), max_y.item(), min_x.item(), max_x.item()
    
    h_padding = int((max_y - min_y) * padding_percent)
    w_padding = int((max_x - min_x) * padding_percent)
    
    y1 = max(0, min_y - h_padding)
    y2 = min(img_h, max_y + h_padding)
    x1 = max(0, min_x - w_padding)
    x2 = min(img_w, max_x + w_padding)
    
    if not square_crop:
        return (y1, y2, x1, x2)
    
    current_height = y2 - y1
    current_width = x2 - x1
    
    side_length = max(current_height, current_width)
    
    center_y = (y1 + y2) // 2
    center_x = (x1 + x2) // 2
    
    half_side = side_length // 2
    
    square_y1 = center_y - half_side
    square_y2 = center_y + half_side
    square_x1 = center_x - half_side
    square_x2 = center_x + half_side
    
    if square_y1 < 0:
        shift = -square_y1
        square_y1 = 0
        square_y2 = min(img_h, square_y2 + shift)
    elif square_y2 > img_h:
        shift = square_y2 - img_h
        square_y2 = img_h
        square_y1 = max(0, square_y1 - shift)
    
    if square_x1 < 0:
        shift = -square_x1
        square_x1 = 0
        square_x2 = min(img_w, square_x2 + shift)
    elif square_x2 > img_w:
        shift = square_x2 - img_w
        square_x2 = img_w
        square_x1 = max(0, square_x1 - shift)
    
    final_height = square_y2 - square_y1
    final_width = square_x2 - square_x1
    final_side = min(final_height, final_width)
    
    center_y = (square_y1 + square_y2) // 2
    center_x = (square_x1 + square_x2) // 2
    half_final_side = final_side // 2
    
    final_y1 = center_y - half_final_side
    final_y2 = center_y + half_final_side
    final_x1 = center_x - half_final_side
    final_x2 = center_x + half_final_side
    
    return (final_y1, final_y2, final_x1, final_x2) 