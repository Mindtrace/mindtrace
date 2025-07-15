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
    cam14: 0.6  # 60% of available images from cam14
    cam15: 0.4  # 40% of available images from cam15
    # Total proportions must equal 1.0
```

### 4. Download All Available Cameras (No Camera Filtering)
```yaml
# Remove or comment out the sampling section entirely
# sampling:
#   cameras:
#     - cam14
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
    - cam14  # Simple list format
    # OR
    cam14: 0.6  # Dictionary format with proportions
    cam15: 0.4

# Date range for sampling
start_date: "2025-06-30"
end_date: "2025-07-01"

# Download settings
download_path: "/path/to/download/directory"
max_workers: 8  # Number of parallel download threads
``` 