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

This script is a comprehensive pipeline for processing spatter annotations from Label Studio, generating segmentation masks, and publishing versioned datasets to a Hugging Face-based datalake.

### Key Concepts

The pipeline operates in two main modes, controlled by the `processing_mode` key in your configuration file.

1.  **`from_scratch`**: This mode is used to create the very first version of a dataset. It processes a full list of Label Studio projects, performs all transformations, and publishes the result as `v1.0.0` (or as specified). It can optionally merge this new data with a pre-existing dataset from the datalake.

2.  **`incremental`**: This mode is used to update an existing dataset. It starts from a local, previously generated dataset (`base_dataset_path`), processes *only* the new Label Studio projects you specify, merges them, and publishes the final result. You need to make a dataset with a new name v1.0.0

### Configuration Guide

#### 1. Spatter Data Configuration

You can generate different types of spatter datasets by modifying two boolean flags.

##### A. Large Spatter Only
This configuration ignores any annotations labeled as `small_spatter`.

```yaml
# spatter_config.yaml
keep_small_spatter: false
separate_class: false
```

##### B. Merged Spatter (Large + Small as one class)
This configuration includes `small_spatter` annotations but treats them as the standard `spatter` class.

```yaml
# spatter_config.yaml
keep_small_spatter: true
separate_class: false
```

##### C. Dual Class Spatter (Large and Small as separate classes)
This configuration keeps both `spatter` and `small_spatter` and assigns them different class IDs for segmentation.

```yaml
# spatter_config.yaml
keep_small_spatter: true
separate_class: true
```

---

### 2. Workflow Examples

Here is how you would configure the pipeline for a typical end-to-end workflow.

#### Step 1: Running `from_scratch`

Use this configuration to create your initial dataset (`v1.0.0`). This example processes two projects and also merges them with a remote "free zone" dataset.

**`configs/my_dataset_scratch.yaml`**
```yaml
processing_mode: from_scratch

# The directory where temporary files will be stored. A unique sub-folder is created for each run.
download_dir: "/path/to/local/work_directory/"

huggingface:
  # The name for your NEW dataset on the datalake
  dataset_name: "my-new-spatter-dataset"
  version: "1.0.0"

  # (Optional) Merge with a remote dataset during the scratch run
  existing_dataset: "spatter-free-zone-detection-segmentation-data"
  existing_version: "1.0.0"

label_studio:
  project_list:
    - "LabelStudio-Project-A"
    - "LabelStudio-Project-B"
  # ... other ls configs
  
# ... other configs (gcp, workers, spatter, etc.)
```
**To run:**
```bash
python spatter_datalake.py --config configs/my_dataset_scratch.yaml
```
After this run completes, look for the output line telling you the unique run directory, which you will need for the next step.
`Created temporary run directory: /path/to/local/work_directory/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`


#### Step 2: Running `incremental`

After creating the base dataset, use this configuration to add a new project to it.

**`configs/my_dataset_incremental.yaml`**
```yaml
processing_mode: incremental

incremental_update:
  # IMPORTANT: This is the full path to the output from the 'from_scratch' run.
  base_dataset_path: "/path/to/local/work_directory/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  
  # List ONLY the new projects to be processed and added.
  new_projects:
    - "LabelStudio-Project-C"
    
  # The version for the final, updated dataset.
  new_version: "1.0.0"

```
**To run:**
```bash
python spatter_datalake.py --config configs/my_dataset_incremental.yaml
```
This will create a new dataset named **"my-new-spatter-dataset"** with version **"1.0.0"** on the datalake, containing data from projects A, B, and C. 