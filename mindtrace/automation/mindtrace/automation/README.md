## Requirements

### Environment Variables
Create a `.env` file in the project root with your database credentials:
```bash
DATABASE_NAME=your_database_name
DATABASE_USERNAME=your_username
DATABASE_PASSWORD=your_password
DATABASE_HOST_NAME=your_host_ip
DATABASE_PORT=your_port_number
```

### GCP Credentials
Ensure you have a valid GCP service account JSON file and update the path in your config.

## Installation

1. Sync dependencies:
```bash
cd mindtrace/automation
uv sync
```

2. Create your `.env` file with database credentials

3. Update `images_config.yaml` with your settings

## Usage

### Image Download
```bash
cd mindtrace/automation/mindtrace/automation
uv run python -m download_images --config configs/images_config.yaml
```

### Inference Pipeline
```bash
cd mindtrace/automation/mindtrace/automation
uv run python -m infer_folder --config configs/test_config.yaml
```

## Inference Pipeline Features

### Supported Input Types
The inference pipeline can process:
- **Single Images**: Direct path to an image file
- **Folders**: All images in a directory
- **Subfolders**: Recursively processes all images in subdirectories

### Export Types
Each model can export results in different formats:
- **Mask**: Semantic segmentation masks (PNG format)
- **Bounding Box**: Object detection boxes (YOLO format)

### Output Structure
The pipeline creates a structured output directory:
```
output_folder/
├── images/           # Original images
├── raw_masks/        # Segmentation masks (PNG)
├── boxes/           # Bounding boxes (YOLO format)
└── visualizations/   # Overlay visualizations (JPG)
```

### Model Loading
The pipeline automatically:
1. Downloads models from GCS if not available locally
2. Loads multiple models for different tasks
3. Handles different model types (object detection, segmentation)
4. Manages model versions and metadata

## Configuration Examples

### 1. Download All Images from a Single Camera (100%)
```yaml
sampling:
  cameras:
    - cam14  # Downloads 100% of available images from cam14
```

### 2. Download All Images from Multiple Cameras (100% each)
```yaml
sampling:
  cameras:
    - cam14
    - cam15
    - cam16  # Each camera gets 100% of its available images
```

### 3. Download Specific Proportions from Multiple Cameras
```yaml
sampling:
  cameras:
    cam14:
      proportion: 0.6  # 60% of available images from cam14
    cam15:
      proportion: 0.4  # 40% of available images from cam15
```

### 4. Download Exact Number of Images per Camera
```yaml
sampling:
  cameras:
    cam14:
      number: 100  # Exactly 100 images from cam14
    cam15:
      number: 50   # Exactly 50 images from cam15
```

### 5. Mixed Proportions and Numbers
```yaml
sampling:
  cameras:
    cam14:
      proportion: 0.1  # 10% of available images
      number: 100      # OR specify exact number (number takes precedence)
    cam15:
      proportion: 0.1  # 10% of available images
      # number: 50    # Uncomment to use exact number instead
```

### 6. Download All Available Cameras (No Camera Filtering)
```yaml
# Remove or comment out the sampling section entirely
# sampling:
#   cameras:
#     - cam14
```

### 7. Reproducible Sampling with Random Seed
```yaml
# Add seed for reproducible results
seed: 42  # Same seed = same images every time
```

### 8. Inference Pipeline Configuration
```yaml
# Model registry settings
task_name: "sfz_pipeline"  # Registered task name
version: "v2.1"            # Model version

# Inference configuration
inference_list:
  zone_segmentation: "mask"           # Export segmentation masks
  spatter_segmentation: "bounding_box" # Export bounding boxes

# Output settings
output_folder: "/path/to/output"
threshold: 0.4              # Confidence threshold
save_visualizations: True   # Generate overlay images
```

### 9. Complete Pipeline Example
```yaml
# Database and GCS settings
gcp:
  data_bucket: "your-data-bucket"
  weights_bucket: "your-weights-bucket"
  base_folder: "models"
  credentials_file: "/path/to/credentials.json"

# Image sampling
sampling:
  cameras:
    cam14:
      number: 10
    cam15:
      number: 10

# Date range
start_date: "2025-06-30"
end_date: "2025-07-01"

# Download settings
download_path: "/path/to/downloads"
max_workers: 8

# Inference pipeline
task_name: "sfz_pipeline"
version: "v2.1"
inference_list:
  zone_segmentation: "mask"
  spatter_segmentation: "bounding_box"

# Output settings
output_folder: "/path/to/results"
threshold: 0.4
save_visualizations: True
```

## Configuration File Structure

```yaml
# Database queries
database_queries:
  get_images_by_date: |
    # Your SQL query here

# Google Cloud Storage settings
gcp:
  data_bucket: "your-data-bucket"
  weights_bucket: "your-weights-bucket"
  base_folder: "models"
  credentials_file: "/path/to/credentials.json"

# Image sampling configuration
sampling:
  cameras:
    # Option 1: Simple list format (100% each)
    - cam14
    - cam15
    
    # Option 2: Dictionary format with proportions
    cam14:
      proportion: 0.6
    cam15:
      proportion: 0.4
    
    # Option 3: Dictionary format with exact numbers
    cam14:
      number: 100
    cam15:
      number: 50
    
    # Option 4: Mixed format (number takes precedence)
    cam14:
      proportion: 0.1
      number: 100  # This will be used, proportion ignored

# Date range for sampling
start_date: "2025-06-30"
end_date: "2025-07-01"

# Random seed for reproducible sampling (optional)
seed: 42

# Download settings
download_path: "/path/to/download/directory"
max_workers: 8  # Number of parallel download threads

# Inference pipeline settings
task_name: "your_pipeline_name"
version: "v1.0"
inference_list:
  task1: "mask"
  task2: "bounding_box"

# Output settings
output_folder: "/path/to/output"
threshold: 0.4
save_visualizations: True
```

## Sampling Options

### Camera Configuration
Each camera can be configured with different sampling methods:

1. **Proportion-based**: Use `proportion` to sample a percentage of available images
2. **Number-based**: Use `number` to sample an exact number of images
3. **Mixed**: Specify both - `number` takes precedence over `proportion`
4. **Default**: If neither is specified, takes all available images (100%)

### Random Seed
- Add `seed: 42` to your config for reproducible sampling
- Same seed = same images every time
- Useful for debugging and consistent testing
- Optional - omit for random sampling

### Behavior Rules
- **Proportion only**: Samples `proportion * total_available_images`
- **Number only**: Takes exactly `number` images (or all if less available)
- **Both specified**: Prints warning and uses `number`
- **Neither specified**: Takes all available images
- **Seed specified**: Ensures reproducible random sampling

## Inference Pipeline Options

### Export Types
Each model task can export results in different formats:

1. **Mask Export**: 
   - Generates semantic segmentation masks
   - Saves as PNG files preserving class values
   - Creates colored overlay visualizations
   - Useful for segmentation tasks

2. **Bounding Box Export**:
   - Generates object detection bounding boxes
   - Saves in YOLO format with confidence scores
   - Creates box overlay visualizations
   - Useful for detection tasks

### Input Processing
The pipeline automatically handles:
- **Single Images**: Direct file path processing
- **Folder Processing**: All images in a directory
- **Subfolder Recursion**: Processes all subdirectories
- **Format Support**: JPG, PNG, BMP, TIFF, WebP

### Output Organization
Results are organized by:
- **Original Images**: Copied to `images/` folder
- **Raw Masks**: Saved to `raw_masks/` folder
- **Bounding Boxes**: Saved to `boxes/` folder
- **Visualizations**: Saved to `visualizations/` folder

### Model Management
The pipeline handles:
- **Automatic Downloads**: Models from GCS if not local
- **Version Control**: Specific model versions
- **Multi-Model Loading**: Multiple tasks simultaneously
- **Device Optimization**: CPU/GPU selection
- **Error Handling**: Graceful failure recovery 