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

```bash
cd mindtrace/automation/mindtrace/automation
uv run python -m download_images --config configs/images_config.yaml
```

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

## Configuration File Structure

```yaml
# Database queries
database_queries:
  get_images_by_date: |
    # Your SQL query here

# Google Cloud Storage settings
gcp:
  bucket: "your-bucket-name"
  credentials_file: "/path/to/your/credentials.json"

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