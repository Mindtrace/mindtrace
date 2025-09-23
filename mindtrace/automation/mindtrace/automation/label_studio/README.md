## Label Studio API Usage

This guide walks you through setting up a local Label Studio instance and includes a hands-on exercise using the Label Studio APIs available in the mindtrace-automation package. The API usage code is also available in [sample usage file](./../../../../../samples/automation/labelstudio/sample_usage.py) for direct execution.

### Run Label Studio locally (sample setup)

Use the docker compose file provided in this repo to spin up Label Studio with persistent data.

Compose file location: [docker compose](../../../../../samples/automation/labelstudio/docker-compose.yml)

Quick start:

1) Navigate to the compose directory
2) Start Label Studio

```bash
docker compose up -d
```

3) Open the UI and Signup for first time login

```text
http://localhost:8080
```

Notes:
- The volume `./data` persists Label Studio database and media under the compose directory.
- If you see a permission error on `/label-studio/data/media`, the compose file already sets `user: "0:0"` to resolve it.
- To stop and remove the container: `docker compose down` (add `-v` to remove volumes if you want a clean state).


### User Token Setup
To use the Label Studio Client, you need two things:

1. Your running Label Studio URL
2. An Access Token (API token) from the Label Studio UI

#### Steps to obtain the Access Token:

1. In the Label Studio UI, click on your profile icon in the top-right corner.
2. Select `Accounts & Settings`.
3. Copy the displayed `Access Token`.

#### If you don’t see the token:

1. Open the `Organization` Settings from the left sidebar (hover menu).
2. Navigate to API Token Settings and enable `Legacy Tokens`.
3. Go back to `Accounts & Settings` and copy your `Access Token`.


### Sample Usage
The following examples demonstrate how the Python-based APIs can be used to create and manage annotation projects in Label Studio.

#### Labelling Setup in Label Studio
Before working with projects via the API, it’s helpful to understand how labeling setups are defined in the Label Studio UI.
1. In the Label Studio interface, click Create Project.
2. Go to the `Labeling Setup` tab.
3. Here you can choose from multiple predefined templates for different machine learning tasks, such as:
    - Computer Vision: Segmentation, Classification, Object Detection
    - NLP: Text Classification, Named Entity Recognition
    - Time Series: Sequence labeling and more
4. For our common use case, select Object Detection with Bounding Boxes.
In the Code section, you will see an XML configuration. This XML is the core definition of the labeling interface — it specifies the input type, the label set, and the task type. For example, the `RectangleLabels` tag is used to define bounding boxes in object detection tasks.

```
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="Cat" background="green"/>
    <Label value="Apple" background="blue"/>
  </RectangleLabels>
</View>
```
This configuration means:
- An image (<Image>) will be displayed for annotation.
- Annotators can draw bounding boxes (<RectangleLabels>) on the image.
- Two possible classes are available: Cat (green) and Apple (blue).


### Sample Project Creation
1. Create a Project in Label studio

```python
#Initialize the LabelStudio Class
from mindtrace.automation.label_studio.label_studio_api import LabelStudio

url="http://localhost:8080"
api_key="XXXX"
#Labeling Setup
label_config = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="Cat" background="green"/>
    <Label value="Apple" background="blue"/>
  </RectangleLabels>
</View>
"""
ls = LabelStudio(url=url, api_key=api_key)
ls.create_project(project_name="test_project", description="Test project", label_config=label_config)
```

The UI should display a `test_project` now.

### Import Tasks: Direct Upload
1. To create labelling task in `test_project` using locally available images use below snippet. Here in the example, locally available sample images are directly uploaded to label studio server and are hence not the recommended way.
```python
project = ls.get_project(project_name="test_project")
sample_dir = str((Path(__file__).parent / "sample_images").resolve())
created = ls.create_tasks_from_images(project_name="test_project", local_dir=sample_dir)
print(f"Created {created} tasks in project '{project.title}' (ID: {project.id})")
```
2. The UI should display two tasks with images which can be annotated.

### Import Tasks: GCP Cloud Storage
Imagine usecase where you would require to import images directly from GCP cloud storage below snippet demonstrates the usage.
For the use case sample images are available at `mt-label-studio-bucket/samples` bucket
```python
google_application_credentials = "path/to/json"
# 3.1 Create GCP storage
try:
  storage = ls.create_gcp_storage(project_name="test_project", 
                                  bucket="mt-label-studio-bucket", 
                                  prefix="samples", storage_type="import", 
                                  use_blob_urls=True,presign=False,
                                  google_application_credentials=google_application_credentials,regex_filter=".*jpg")
  print(f"Created GCP storage id: {storage['id']} in project '{project.title}' (ID: {project.id})")
except ValueError:
  print(f"GCP storage already exists in project '{project.title}' (ID: {project.id})")

# 3.2 Sync GCP storage
sync_gcp_storage = ls.sync_gcp_storage(project_name="test_project",storage_prefix="samples")
print(f"Synced GCP storage in project '{project.title}' (ID: {project.id})")
```

### Get Annotations
The users can annotate or label the tasks in Label Studio GUI and use below snippet to get the annotations.
```python
annotations = ls.get_annotations(project_name="test_project")
for annotation in annotations:
  for key,value in annotation.items():
    print(f"{key}:{value}")
  print("--------------------------------")
```