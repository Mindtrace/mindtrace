### Label Studio Pipeline: Usage Guide

This document explains how to use the Label Studio pipeline to:
- Download images from GCS using database queries
- Run inference and export predictions
- Convert predictions to Label Studio JSON and create/sync a project

It supports two data selection modes:
- Query by date range
- Query by serial numbers (Basler-only)

---

## 1) Prerequisites
- Database credentials available as environment variables (from `envs/database.env` or exported):
  - `DATABASE_NAME`, `DATABASE_USERNAME`, `DATABASE_PASSWORD`, `DATABASE_HOST_NAME`, `DATABASE_PORT`
- GCP credentials file(s) present and paths set in YAML.
- Label Studio API URL and key if you want to create a project automatically.

---

## 2) Configuration (YAML)
Key sections and options supported by the pipeline.

- `pipeline_type`: One of `sfz` or `laser` (controls model pipeline)
- `data_source`: `gcp` (downloads then runs inference) or `local` (runs inference on a local folder)
- `database_queries.query_type`:
  - `get_images_by_date`: query by date/time window
  - `get_images_by_serial_number`: query by Basler serial numbers

### 2.1 GCP
- `gcp.data_bucket`: GCS bucket where source images reside
- `gcp.credentials_file`: Path to GCP credentials JSON (used for downloading images and uploads)
- `gcp.weights_bucket`, `gcp.base_folder`: Model weights location

### 2.2 Label Studio
- `label_studio.upload_enabled`: Set `true` if you want to create JSONs and a project
- `label_studio.bucket`: GCS bucket to upload Label Studio JSON files
- `label_studio.prefix`: Prefix/folder in the bucket for job JSONs
- `label_studio.api.url`, `label_studio.api.api_key`, `label_studio.api.gcp_credentials_path`: API configuration
- `label_studio.project.title`, `label_studio.project.description`: Project metadata
- `label_studio.interface_config`: XML configuration for the LS labeling UI

### 2.3 Download/Inference
- `download_path`: Local directory where images will be saved
- `max_workers`: Parallel download workers
- `inference_list`: Which tasks and export types to run (e.g., `mask` / `bounding_box`)
- `task_name`, `version`: Model selection
- `output_folder`: Where inference outputs and Label Studio JSONs will be written
- `threshold`, `save_visualizations`, `overwrite_masks`: Inference options

### 2.4 Selecting Images
- Date mode (`get_images_by_date`):
  - `start_date`: YYYY-MM-DD
  - `end_date`: YYYY-MM-DD
  - Optional: `samples_per_day` to limit per-day sampling
  - Optional: `sampling.cameras` to sample by camera (proportion or fixed number)
- Serial number mode (`get_images_by_serial_number`):
  - Provide serials via:
    - `serial_numbers`: list of strings, or
    - `serial_numbers_file`: path to a text file (one serial per line; `#` and blank lines ignored)
  - In serial mode:
    - Date range is ignored
    - Label Studio deduplication is skipped
    - Camera sampling is skipped (all matches are downloaded)

---

## 3) Example Configs

### 3.1 Query by serial numbers (GCP)
```yaml
pipeline_type: "sfz"
data_source: gcp

database_queries:
  query_type: "get_images_by_serial_number"

gcp:
  data_bucket: "<your-images-bucket>"
  weights_bucket: "<your-weights-bucket>"
  base_folder: "sfz"
  credentials_file: "/absolute/path/to/google_creds.json"

label_studio:
  upload_enabled: true
  bucket: "<your-ls-json-bucket>"
  prefix: "labelstudio-jsons"
  api:
    url: "https://your-label-studio"
    api_key: "<key>"
    gcp_credentials_path: "/absolute/path/to/google_creds.json"
  project:
    title: "Inference Run"
    description: "Predictions for review"

# Download/inference
download_path: "/absolute/path/to/downloads"
max_workers: 16
output_folder: "/absolute/path/to/output"

# Provide serials via file (recommended when large)
serial_numbers_file: "/absolute/path/to/serial_numbers.txt"

# Models / tasks
task_name: "sfz_pipeline"
version: "v4.0"
inference_list:
  zone_segmentation: "mask"
  spatter_segmentation: "bounding_box"
mask_tasks:
  - "zone_segmentation"
threshold: 0.01
save_visualizations: false
overwrite_masks: false
```

`serial_numbers.txt` format:
```
# one per line
num1
num2
...
```

### 3.2 Query by date range (GCP)
```yaml
pipeline_type: "sfz"
data_source: gcp

database_queries:
  query_type: "get_images_by_date"

gcp:
  data_bucket: "<your-images-bucket>"
  weights_bucket: "<your-weights-bucket>"
  base_folder: "sfz"
  credentials_file: "/absolute/path/to/google_creds.json"

label_studio:
  upload_enabled: true
  bucket: "<your-ls-json-bucket>"
  prefix: "labelstudio-jsons"
  api:
    url: "https://your-label-studio"
    api_key: "<key>"
    gcp_credentials_path: "/absolute/path/to/google_creds.json"
  project:
    title: "Inference Run"
    description: "Predictions for review"

# Date selection
start_date: "2025-08-06"
end_date: "2025-08-08"
# Optional sampling controls
samples_per_day: 50
sampling:
  cameras:
    "Basler:cam1": { number: 100 }
    "Basler:cam2": { proportion: 0.2 }

# Download/inference
download_path: "/absolute/path/to/downloads"
max_workers: 16
output_folder: "/absolute/path/to/output"

# Models / tasks
task_name: "sfz_pipeline"
version: "v4.0"
inference_list:
  zone_segmentation: "mask"
  spatter_segmentation: "bounding_box"
mask_tasks:
  - "zone_segmentation"
threshold: 0.01
save_visualizations: false
overwrite_masks: false
```

---

## 4) How to Run

### 4.1 Download only (no inference/LS)
If you only want to download images:
```bash
python mindtrace/automation/mindtrace/automation/download_images.py \
  --config /absolute/path/to/your_config.yaml
```
- Saves images under `download_path/<timestamp>/`.
- Writes a GCS mapping at `download_path/<timestamp>/gcs_paths.json` (in GCP mode).

### 4.2 Full pipeline (inference + LS JSONs + project)
```bash
python mindtrace/automation/mindtrace/automation/label_studio_pipeline.py \
  --config /absolute/path/to/your_config.yaml
```
- GCP mode downloads images first, then runs inference and produces Label Studio JSONs in `output_folder`.
- Automatically uploads JSONs to the LS GCS bucket/prefix and creates a Label Studio project.