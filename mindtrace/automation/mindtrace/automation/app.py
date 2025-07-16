import streamlit as st
import yaml
import os
import uuid
from dotenv import load_dotenv
import tempfile
import copy
from mindtrace.automation.modelling.inference import Pipeline, ExportType
from mindtrace.automation.download_images import ImageDownload

# Load environment variables from .env file
load_dotenv(dotenv_path='envs/database.env')

def run_pipeline(config):
    st.write("Running pipeline with the following configuration:")
    st.json(config)
    
    # Get the data from the database
    # Check if env variables are loaded
    db_name = os.getenv('DATABASE_NAME')
    db_user = os.getenv('DATABASE_USERNAME')
    db_password = os.getenv('DATABASE_PASSWORD')
    db_host = os.getenv('DATABASE_HOST_NAME')
    db_port = os.getenv('DATABASE_PORT')

    if not all([db_name, db_user, db_password, db_host, db_port]):
        st.error("Database environment variables are not set. Please check your `database.env` file.")
        st.stop()
    
    assert db_name is not None
    assert db_user is not None
    assert db_password is not None
    assert db_host is not None
    assert db_port is not None

    with st.spinner("Downloading images..."):
        try:
            downloader = ImageDownload(
                database=db_name,
                user=db_user,
                password=db_password,
                host=db_host,
                port=db_port,
                gcp_credentials_path=config['gcp']['credentials_file'],
                gcp_bucket=config['gcp']['data_bucket'],
                local_download_path=config['download_path'],
                config=config
            )
            downloader.get_data()
            st.success("Image download complete.")
        except Exception as e:
            st.error(f"Failed to download images: {e}")
            st.stop()

    # Run the inference
    with st.spinner("Running inference..."):
        try:
            pipeline = Pipeline(
                credentials_path=config['gcp']['credentials_file'],
                bucket_name=config['gcp']['weights_bucket'],
                base_folder=config['gcp']['base_folder'],
                local_models_dir="./tmp",
                overwrite_masks=config['overwrite_masks']
            )

            pipeline.load_pipeline(
                task_name=config['task_name'],
                version=config['version'],
                inference_list=config['inference_list']
            )

            if os.path.exists(config['download_path']):
                export_types = {}
                for task_name, export_type_str in config['inference_list'].items():
                    if export_type_str == "mask":
                        export_types[task_name] = ExportType.MASK
                    elif export_type_str == "bounding_box":
                        export_types[task_name] = ExportType.BOUNDING_BOX

                summary = pipeline.run_inference_on_path(
                    input_path=config['download_path'],
                    output_folder=config['output_folder'],
                    export_types=export_types,
                    threshold=config['threshold'],
                    save_visualizations=config['save_visualizations']
                )

                if summary and summary.get('processed_images', 0) > 0:
                    st.success("Inference completed successfully.")
                    st.write("Inference Summary:")
                    st.json(summary)
                else:
                    st.warning("Inference completed, but no images were processed.")
            else:
                st.error(f"Input folder not found: {config['download_path']}")
        except Exception as e:
            st.error(f"Inference failed: {e}")
            st.stop()


def main():
    st.set_page_config(layout="wide")
    st.title("Inference Pipeline Runner")

    # Load default config
    config_path = 'configs/test_config.yaml'
    with open(config_path) as f:
        default_config = yaml.safe_load(f)

    # Initialize session state from the default config if it's not already set
    if 'cameras' not in st.session_state:
        st.session_state.cameras = copy.deepcopy(default_config['sampling']['cameras'])
    if 'inference_tasks' not in st.session_state:
        st.session_state.inference_tasks = copy.deepcopy(default_config['inference_list'])

    # Use a deep copy of the default config to preserve all keys
    config = copy.deepcopy(default_config)

    st.header("Configuration")

    with st.expander("GCP Settings", expanded=True):
        config['gcp']['data_bucket'] = st.text_input("Data Bucket", value=config['gcp']['data_bucket'])
        config['gcp']['weights_bucket'] = st.text_input("Weights Bucket", value=config['gcp']['weights_bucket'])
        config['gcp']['base_folder'] = st.text_input("Base Folder", value=config['gcp']['base_folder'])
        
        uploaded_creds = st.file_uploader("GCP Credentials JSON", type=['json'])
        if uploaded_creds is not None:
            # On windows, NamedTemporaryFile is not accessible by other processes if not closed.
            # So, we create, write, close and then use the name.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w') as tmp:
                tmp.write(uploaded_creds.getvalue().decode("utf-8"))
                config['gcp']['credentials_file'] = tmp.name
            st.success(f"Uploaded credentials to {config['gcp']['credentials_file']}")
        else:
            st.info(f"Using default credentials path: {config['gcp']['credentials_file']}")

    with st.expander("Image Sampling", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            config['start_date'] = st.text_input("Start Date", value=str(config['start_date']))
        with col2:
            config['end_date'] = st.text_input("End Date", value=str(config['end_date']))
        
        config['seed'] = st.number_input("Random Seed", value=config['seed'])

        st.subheader("Cameras")
        
        # Display editable fields for each camera in the session state
        camera_names = list(st.session_state.cameras.keys())
        for cam_name in camera_names:
            st.write(f"**Camera: {cam_name}**")
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                num_images = st.number_input(
                    f"Number of images",
                    min_value=0,
                    value=st.session_state.cameras[cam_name].get('number', 0),
                    step=1,
                    key=f"{cam_name}_number"
                )
                st.session_state.cameras[cam_name]['number'] = num_images
            with c2:
                proportion = st.slider(
                    f"Proportion of images",
                    min_value=0.0,
                    max_value=1.0,
                    value=st.session_state.cameras[cam_name].get('proportion', 0.0),
                    step=0.01,
                    key=f"{cam_name}_proportion"
                )
                st.session_state.cameras[cam_name]['proportion'] = proportion
            with c3:
                st.write("") # Spacer
                if st.button(f"Remove", key=f"remove_cam_{cam_name}"):
                    del st.session_state.cameras[cam_name]
                    st.rerun()
        
        st.markdown("---")
        st.write("Add a new camera")
        new_cam_name = st.text_input("New Camera Name")
        if st.button("Add Camera"):
            if new_cam_name and new_cam_name not in st.session_state.cameras:
                st.session_state.cameras[new_cam_name] = {'number': 1, 'proportion': 0.1}
                st.rerun()
            elif not new_cam_name:
                st.warning("Please enter a camera name.")
            else:
                st.warning(f"Camera '{new_cam_name}' already exists.")


    with st.expander("Paths and Workers", expanded=True):
        base_download_path = st.text_input("Base Download Path", value=config.get('download_path', 'downloads'))
        base_output_folder = st.text_input("Base Output Folder", value=config.get('output_folder', 'test_output'))
        config['max_workers'] = st.number_input("Max Workers", value=config['max_workers'], min_value=1, step=1)

    with st.expander("Inference Settings", expanded=True):
        config['task_name'] = st.text_input("Task Name", value=config['task_name'])
        config['version'] = st.text_input("Version", value=config['version'])
        
        st.subheader("Inference Tasks")
        
        # Display current tasks with a remove button
        tasks_to_remove = []
        for task_name, export_type in st.session_state.inference_tasks.items():
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"**Task:** `{task_name}`, **Export:** `{export_type}`")
            with col2:
                if st.button(f"Remove", key=f"remove_task_{task_name}"):
                    tasks_to_remove.append(task_name)

        if tasks_to_remove:
            for task in tasks_to_remove:
                del st.session_state.inference_tasks[task]
            st.rerun()

        st.markdown("---")
        st.write("Add a new inference task:")
        # A realistic list of available tasks
        available_tasks = ['zone_segmentation', 'spatter_segmentation', 'spatter_detection']
        addable_tasks = [t for t in available_tasks if t not in st.session_state.inference_tasks]

        if addable_tasks:
            col1, col2, col3 = st.columns([2,2,1])
            with col1:
                new_task_name = st.selectbox("Available Tasks", options=addable_tasks, key="new_task_name")
            with col2:
                new_export_type = st.selectbox("Export Type", options=["mask", "bounding_box"], key="new_export_type")
            with col3:
                st.write("") # Spacer
                if st.button("Add Task"):
                    st.session_state.inference_tasks[new_task_name] = new_export_type
                    st.rerun()
        else:
            st.info("All available tasks have been added.")

        config['threshold'] = st.slider("Threshold", min_value=0.0, max_value=1.0, value=config['threshold'], step=0.05)
        config['save_visualizations'] = st.checkbox("Save Visualizations", value=config['save_visualizations'])
        config['overwrite_masks'] = st.checkbox("Overwrite Masks", value=config['overwrite_masks'])

    if st.button("Run Inference Pipeline"):
        run_id = str(uuid.uuid4())
        
        # Update config from session state before running
        config['sampling']['cameras'] = st.session_state.cameras
        config['inference_list'] = st.session_state.inference_tasks

        config['download_path'] = os.path.join(base_download_path, run_id)
        config['output_folder'] = os.path.join(base_output_folder, run_id)
        
        os.makedirs(config['download_path'], exist_ok=True)
        os.makedirs(config['output_folder'], exist_ok=True)

        run_pipeline(config)

        # Clean up the temporary credentials file
        if uploaded_creds is not None and os.path.exists(config['gcp']['credentials_file']):
            os.remove(config['gcp']['credentials_file'])


if __name__ == "__main__":
    main() 