import argparse
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import os
from dotenv import load_dotenv
import tempfile
import pandas as pd

from mindtrace.automation.database.database_connection import DatabaseConnection
from mindtrace.storage.gcs import GCSStorageHandler

# Load environment variables from .env file
load_dotenv("envs/database.env")

class ImageDownload:
    def __init__(
        self,
        database: str,
        user: str,
        password: str,
        host: str,
        port: str,
        gcp_credentials_path: str,
        gcp_bucket: str,
        local_download_path: str,
        config: Dict[str, dict]
    ):
        """Initialize database and GCP connections."""
        self.config = config
        query_config = self.config.get('database_queries', {})
        if not query_config:
            raise ValueError("No database_queries section found in config file")
        
        self.db_conn = DatabaseConnection(
            database=database,
            user=user,
            password=password,
            host=host,
            port=int(port),
            query_config=query_config
        )
        
        self.gcp_manager = GCSStorageHandler(
            bucket_name=gcp_bucket,
            credentials_path=gcp_credentials_path
        )
        
        self.local_download_path = Path(local_download_path)
        self.local_download_path.mkdir(parents=True, exist_ok=True)

    def get_camera_proportions(self, config: Dict[str, dict]) -> Dict[str, float]:
        if 'sampling' in config and 'cameras' in config['sampling']:
            cameras_config = config['sampling']['cameras']
            cameras = {}
            
            # Handle list of camera names (default to 100% each)
            if isinstance(cameras_config, list):
                for cam in cameras_config:
                    cameras[cam] = {'proportion': 1.0}
            # Handle dictionary format
            elif isinstance(cameras_config, dict):
                for cam, cfg in cameras_config.items():
                    if isinstance(cfg, dict):
                        # Validate the configuration
                        if 'proportion' in cfg and cfg['proportion'] <= 0:
                            raise ValueError(f"Camera {cam} proportion must be greater than 0, got {cfg['proportion']}")
                        if 'number' in cfg and cfg['number'] <= 0:
                            raise ValueError(f"Camera {cam} number must be greater than 0, got {cfg['number']}")
                        cameras[cam] = cfg
                    elif isinstance(cfg, (int, float)):
                        # Backward compatibility: treat as proportion
                        cameras[cam] = {'proportion': float(cfg)}
                    else:
                        cameras[cam] = {'proportion': 1.0}
        return cameras

    def get_images_by_date(
        self,
        start_date: str,
        end_date: str,
        cameras: Optional[Dict[str, dict]] = None,
        number_samples_per_day: Optional[int] = None,
        seed: Optional[int] = None
    ) -> pd.DataFrame:
        """Get image paths from database within date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            cameras: Dictionary mapping camera names to config dict with 'proportion' and/or 'number'
            number_samples_per_day: Optional number of samples to take per day
            seed: Random seed for reproducible sampling
        """
        df = self.db_conn.get_images_by_date(
            start_timestamp=start_date,
            end_timestamp=end_date,
            number_samples_per_day=number_samples_per_day
        )

        # Set random seed for reproducible sampling
        if seed is not None:
            import random
            random.seed(seed)
            print(f"Using random seed: {seed}")

        if df.empty:
            print("No images found in the specified date range")
            return df

        print(f"Found {len(df)} total images in date range {start_date} to {end_date}")

        available_cameras = df['Camera'].unique()
        print(f"Available cameras: {list(available_cameras)}")

        if cameras is None:
            print("No cameras specified, returning all images")
            return df

        requested_cameras = list(cameras.keys())
        
        found_cameras = [cam for cam in requested_cameras if cam in available_cameras]
        missing_cameras = [cam for cam in requested_cameras if cam not in available_cameras]
        
        if missing_cameras:
            print(f"Warning: Cameras {missing_cameras} not found in data")
        
        if not found_cameras:
            print("No requested cameras found in data")
            return pd.DataFrame()
        
        df = df[df['Camera'].isin(found_cameras)]
        print(f"After camera filtering: {len(df)} images from cameras {found_cameras}")
        
        if len(found_cameras) == 1:
            print(f"Single camera {found_cameras[0]} detected, returning all {len(df)} images")
            return df
        
        total_available = len(df)
        print(f"Auto-detected total: {total_available} images")
        
        sampled_dfs = []
        for camera, config in cameras.items():
            if camera in found_cameras:
                camera_df = df[df['Camera'] == camera]
                if not camera_df.empty:
                    # Check if both proportion and number are specified
                    has_proportion = 'proportion' in config
                    has_number = 'number' in config
                    
                    if has_proportion and has_number:
                        print(f"Warning: Both proportion and number specified for camera {camera}. Using number.")
                    
                    # Use number if specified, otherwise use proportion
                    if has_number:
                        n_samples = min(config['number'], len(camera_df))
                        print(f"Camera {camera}: {len(camera_df)} available, taking {n_samples} (requested: {config['number']})")
                    elif has_proportion:
                        n_samples = int(total_available * config['proportion'])
                        print(f"Camera {camera}: {len(camera_df)} available, taking {n_samples} ({config['proportion']*100:.1f}%)")
                    else:
                        # Default to 100% if neither specified
                        n_samples = len(camera_df)
                        print(f"Camera {camera}: {len(camera_df)} available, taking all {n_samples}")
                    
                    if len(camera_df) > n_samples:
                        camera_df = camera_df.sample(n=n_samples, random_state=seed)
                    sampled_dfs.append(camera_df)
        
        if sampled_dfs:
            df = pd.concat(sampled_dfs)
            print(f"Final selection: {len(df)} images")
        else:
            print("Warning: No images found for specified cameras")
            return pd.DataFrame()
        
        return df

    def download_images(self, df: pd.DataFrame, max_workers: int = 8) -> None:
        """Download images from GCS using paths from database."""
        if df.empty:
            print("No images to download")
            return
            
        for camera in df['Camera'].unique():
            camera_dir = self.local_download_path / camera
            camera_dir.mkdir(exist_ok=True)
            
            camera_df = df[df['Camera'] == camera]
            print(f"\nProcessing {camera}: {len(camera_df)} images")
            
            file_map = {}
            for _, row in camera_df.iterrows():
                filename = Path(row['ImgPath']).name
                local_path = camera_dir / filename
                file_map[row['ImgPath']] = str(local_path)
            
            print(f"Downloading {len(file_map)} files for {camera}...")
            downloaded_paths, errors = self.gcp_manager.download_files(
                file_map, 
                max_workers=max_workers
            )
            
            if errors:
                print(f"Warning: Failed to download {len(errors)} files:")
                for path, error in list(errors.items())[:3]:
                    print(f"  - Failed to download {Path(path).name}")
                    print(f"    Error: {error}")
                if len(errors) > 3:
                    print(f"  ... and {len(errors) - 3} more errors")
    
    def get_data(self):       
        try:
            cameras = self.get_camera_proportions(self.config)
            
            df = self.get_images_by_date(
                start_date=self.config['start_date'],
                end_date=self.config['end_date'],
                cameras=cameras,
                number_samples_per_day=self.config.get('samples_per_day'),
                seed=self.config.get('seed')
            )
            
            os.makedirs('database_data', exist_ok=True)
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            df.to_csv(f'database_data/{timestamp}.csv')
            
            self.download_images(df, max_workers=self.config.get('max_workers', 8))
        except Exception as e:
            print(f"Error: {e}")
            raise e

def main():
    parser = argparse.ArgumentParser(description="Efficiently download images using database and GCS")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()
    
    with open(args.config) as f:
        config = yaml.safe_load(f)
    
    downloader = ImageDownload(
        database=os.getenv('DATABASE_NAME'),
        user=os.getenv('DATABASE_USERNAME'),
        password=os.getenv('DATABASE_PASSWORD'),
        host=os.getenv('DATABASE_HOST_NAME'),
        port=os.getenv('DATABASE_PORT'),
        gcp_credentials_path=config['gcp']['credentials_file'],
        gcp_bucket=config['gcp']['data_bucket'],
        local_download_path=config.get('download_path', 'downloads'),
        config=config
    )
    downloader.get_data()

if __name__ == "__main__":
    main() 