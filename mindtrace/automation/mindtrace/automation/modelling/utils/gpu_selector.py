import torch
import subprocess
import re
import os
from typing import Optional, List, Tuple

def get_gpu_utilization() -> List[Tuple[int, float]]:
    """
    Get GPU utilization for all available GPUs.
    
    Returns:
        List of tuples (gpu_id, utilization_percentage)
    """
    try:
        # Use nvidia-smi to get GPU utilization
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,utilization.gpu', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, check=True)
        
        gpu_utils = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                gpu_id, util = line.split(', ')
                gpu_utils.append((int(gpu_id), float(util)))
        
        return gpu_utils
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        # Fallback: return empty list if nvidia-smi is not available
        return []

def get_gpu_memory_usage() -> List[Tuple[int, float, float]]:
    """
    Get GPU memory usage for all available GPUs.
    
    Returns:
        List of tuples (gpu_id, used_memory_mb, total_memory_mb)
    """
    try:
        # Use nvidia-smi to get GPU memory usage
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, check=True)
        
        gpu_memory = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                gpu_id, used, total = line.split(', ')
                gpu_memory.append((int(gpu_id), float(used), float(total)))
        
        return gpu_memory
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        # Fallback: return empty list if nvidia-smi is not available
        return []

def select_best_gpu(min_memory_gb: float = 4.0, max_utilization: float = 80.0) -> Optional[str]:
    """
    Select the best available GPU based on utilization and memory.
    
    Args:
        min_memory_gb: Minimum required free memory in GB
        max_utilization: Maximum allowed GPU utilization percentage
    
    Returns:
        Device string (e.g., 'cuda:0') or None if no suitable GPU found
    """
    if not torch.cuda.is_available():
        return None
    
    gpu_count = torch.cuda.device_count()
    if gpu_count == 0:
        return None
    
    # Get GPU utilization and memory info
    gpu_utils = get_gpu_utilization()
    gpu_memory = get_gpu_memory_usage()
    
    # Create a mapping of GPU info
    gpu_info = {}
    for gpu_id, util in gpu_utils:
        gpu_info[gpu_id] = {'utilization': util}
    
    for gpu_id, used_mb, total_mb in gpu_memory:
        if gpu_id in gpu_info:
            gpu_info[gpu_id]['used_memory_mb'] = used_mb
            gpu_info[gpu_id]['total_memory_mb'] = total_mb
            gpu_info[gpu_id]['free_memory_mb'] = total_mb - used_mb
            gpu_info[gpu_id]['free_memory_gb'] = (total_mb - used_mb) / 1024.0
    
    # Filter GPUs based on requirements
    suitable_gpus = []
    for gpu_id, info in gpu_info.items():
        if gpu_id >= gpu_count:  # Skip if GPU ID is out of range
            continue
            
        # Check if GPU meets requirements
        if (info.get('utilization', 100) <= max_utilization and 
            info.get('free_memory_gb', 0) >= min_memory_gb):
            suitable_gpus.append((gpu_id, info))
    
    if not suitable_gpus:
        print(f"No suitable GPU found. Requirements: <{max_utilization}% utilization, >{min_memory_gb}GB free memory")
        return None
    
    # Sort by utilization (lowest first), then by free memory (highest first)
    suitable_gpus.sort(key=lambda x: (x[1]['utilization'], -x[1]['free_memory_gb']))
    
    best_gpu_id = suitable_gpus[0][0]
    best_gpu_info = suitable_gpus[0][1]
    
    print(f"Selected GPU {best_gpu_id}: {best_gpu_info['utilization']:.1f}% utilization, "
          f"{best_gpu_info['free_memory_gb']:.1f}GB free memory")
    
    return f"cuda:{best_gpu_id}"

def set_environment_for_best_gpu(min_memory_gb: float = 4.0, max_utilization: float = 80.0) -> str:
    """
    Set environment variables for the best available GPU.
    
    Args:
        min_memory_gb: Minimum required free memory in GB
        max_utilization: Maximum allowed GPU utilization percentage
    
    Returns:
        Selected device string
    """
    device = select_best_gpu(min_memory_gb, max_utilization)
    
    if device is None:
        print("No suitable GPU found, falling back to CPU")
        device = "cpu"
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    else:
        gpu_id = device.split(":")[1]
        os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
        print(f"Set CUDA_VISIBLE_DEVICES to {gpu_id}")
    
    return device

def print_gpu_status():
    """Print current status of all available GPUs."""
    if not torch.cuda.is_available():
        print("CUDA is not available")
        return
    
    gpu_count = torch.cuda.device_count()
    print(f"Found {gpu_count} CUDA device(s)")
    
    gpu_utils = get_gpu_utilization()
    gpu_memory = get_gpu_memory_usage()
    
    for i in range(gpu_count):
        gpu_name = torch.cuda.get_device_name(i)
        util = next((util for gpu_id, util in gpu_utils if gpu_id == i), 0.0)
        memory_info = next((mem for gpu_id, *mem in gpu_memory if gpu_id == i), (0.0, 0.0))
        
        used_mb, total_mb = memory_info
        free_mb = total_mb - used_mb
        free_gb = free_mb / 1024.0
        
        print(f"GPU {i}: {gpu_name}")
        print(f"  Utilization: {util:.1f}%")
        print(f"  Memory: {used_mb:.0f}MB / {total_mb:.0f}MB ({free_gb:.1f}GB free)")
        print() 