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

3. Update your configuration files (`images_config.yaml`, etc.) with your settings.

---

## Image Download & Inference Pipeline

This pipeline is used for downloading images from the database and running inference on them with various models.

### Usage

#### Image Download
```bash
cd mindtrace/automation/mindtrace/automation
uv run python -m download_images --config configs/images_config.yaml
```

#### Inference Pipeline
```bash
cd mindtrace/automation/mindtrace/automation
uv run python -m infer_folder --config configs/images_config.yaml
```

### Configuration Examples

#### 1. Download All Images from a Single Camera (100%)
```yaml
sampling:
  cameras:
    - cam14  # Downloads 100% of available images from cam14
```

#### 2. Download Specific Proportions from Multiple Cameras
```yaml
sampling:
  cameras:
    cam14:
      proportion: 0.6  # 60% of available images from cam14
    cam15:
      proportion: 0.4  # 40% of available images from cam15
```

---

## Spatter Datalake Pipeline (`spatter_datalake.py`)

This script processes Label Studio projects end-to-end: export annotations, download images/masks, split into train/test, optionally crop, and publish a dataset to the datalake.

### Unified Pipeline (no modes)
There is a single unified flow (no more `from_scratch`/`incremental` modes).

High-level steps:
- Export annotations from Label Studio projects listed in `label_studio.project_list`
- Download images, labels, and zone masks
- Perform train/test split with an optional ratio
- Optional cropping per zone configuration
- Build a dataset folder structure with manifests and publish via the datalake client

### Key Config Keys
- `label_studio.project_list`: List of project names to process
- `workers`: Parallelism for downloads/processing
- `zone_class_names`: Class names for zone masks (drawing order)
- `convert_box_to_mask`: If true, convert boxes to masks using SAM
- `train_test_split_ratio`: e.g., `0.2` for 80/20 split
- `cropping.enabled`: Whether to run cropping after splitting
- `cropping.cropping_config_path`: Path to cropping JSON config
- `huggingface`: Datalake publishing configuration (dataset name, version, token/creds)

### Spatter class configuration
Control which spatter annotations are included and how they’re labeled via two flags:
- `keep_small_spatter` (bool)
- `separate_class` (bool)

Examples:

A) Large Spatter Only (ignore `small_spatter`):
```yaml
keep_small_spatter: false
separate_class: false
```

B) Merged Spatter (Large + Small as one class):
```yaml
keep_small_spatter: true
separate_class: false
```

C) Dual Class Spatter (Large and Small as separate classes):
```yaml
keep_small_spatter: true
separate_class: true
```

### Forcing specific projects into a split (overrides)
You can force certain Label Studio projects into `train` or `test` regardless of the automatic ratio via `project_split_overrides`.

Important: Keys are project names (as they appear in `label_studio.project_list`). The pipeline validates names and maps them internally to project IDs.

Example:
```yaml
# ... other configs ...
label_studio:
  project_list:
    - Project_A
    - Project_B
    - Project_C

train_test_split_ratio: 0.2  # 80/20

project_split_overrides:
  Project_A: train  # Force all images from Project_A into train
  Project_C: test   # Force all images from Project_C into test
```

### How to Run
```bash
cd mindtrace/automation/mindtrace/automation
python spatter_datalake.py --config configs/my_spatter_config.yaml
```

On success, you’ll see a unique run directory created and the dataset published (or updated) per your `huggingface` config. 