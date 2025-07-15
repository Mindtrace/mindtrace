import argparse
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import os
from dotenv import load_dotenv

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
        query_config_path: str = None
    ):
        """Initialize database and GCP connections."""
        self.db_conn = DatabaseConnection(
            database=database,
            user=user,
            password=password,
            host=host,
            port=int(port),
            query_config_path=query_config_path
        )
        
        self.gcp_manager = GCSStorageHandler(
            bucket_name=gcp_bucket,
            credentials_path=gcp_credentials_path
        )
        
        self.local_download_path = Path(local_download_path)
        self.local_download_path.mkdir(parents=True, exist_ok=True)

    def get_images_by_date(
        self,
        start_date: str,
        end_date: str,
        cameras: Optional[Dict[str, float]] = None,
        number_samples_per_day: Optional[int] = None
    ) -> pd.DataFrame:
        """Get image paths from database within date range.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            cameras: Dictionary mapping camera names to proportions (if None, get all cameras)
            number_samples_per_day: Optional number of samples to take per day
        """
        df = self.db_conn.get_images_by_date(
            start_timestamp=start_date,
            end_timestamp=end_date,
            number_samples_per_day=number_samples_per_day
        )
        
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
        for camera, proportion in cameras.items():
            if camera in found_cameras:
                camera_df = df[df['Camera'] == camera]
                if not camera_df.empty:
                    n_samples = int(total_available * proportion)
                    print(f"Camera {camera}: {len(camera_df)} available, taking {n_samples} ({proportion*100:.1f}%)")
                    
                    if len(camera_df) > n_samples:
                        camera_df = camera_df.sample(n=n_samples)
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

def main():
    parser = argparse.ArgumentParser(description="Efficiently download images using database and GCS")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()
    
    with open(args.config) as f:
        config = yaml.safe_load(f)
    
    import tempfile
    query_config = config.get('database_queries', {})
    if not query_config:
        raise ValueError("No database_queries section found in config file")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp_file:
        yaml.dump(query_config, tmp_file)
        query_config_path = tmp_file.name
    try:
        downloader = ImageDownload(
            database=os.getenv('DATABASE_NAME'),
            user=os.getenv('DATABASE_USERNAME'),
            password=os.getenv('DATABASE_PASSWORD'),
            host=os.getenv('DATABASE_HOST_NAME'),
            port=os.getenv('DATABASE_PORT'),
            gcp_credentials_path=config['gcp']['credentials_file'],
            gcp_bucket=config['gcp']['bucket'],
            local_download_path=config.get('download_path', 'downloads'),
            query_config_path=query_config_path
        )
        
        cameras = None
        if 'sampling' in config and 'cameras' in config['sampling']:
            cameras_config = config['sampling']['cameras']
            cameras = {}
            
            # Handle list of camera names (default to 100% each)
            if isinstance(cameras_config, list):
                for cam in cameras_config:
                    cameras[cam] = 1.0
            # Handle dictionary format (for backward compatibility)
            elif isinstance(cameras_config, dict):
                for cam, cfg in cameras_config.items():
                    if isinstance(cfg, dict) and 'proportion' in cfg:
                        cameras[cam] = cfg['proportion']
                    elif isinstance(cfg, (int, float)):
                        cameras[cam] = float(cfg)
                    else:
                        cameras[cam] = 1.0
            
            proportions = list(cameras.values())
            if any(p < 1.0 for p in proportions):
                total_proportion = sum(proportions)
                if abs(total_proportion - 1.0) > 0.001: 
                    raise ValueError(
                        f"Camera proportions must add up to 1.0, but got {total_proportion:.3f}. "
                        f"Current proportions: {dict(zip(cameras.keys(), proportions))}"
                    )
        
        df = downloader.get_images_by_date(
            start_date=config['start_date'],
            end_date=config['end_date'],
            cameras=cameras,
            number_samples_per_day=config.get('samples_per_day')
        )
        
        os.makedirs('database_data', exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        df.to_csv(f'database_data/{timestamp}.csv')
        
        downloader.download_images(df, max_workers=config.get('max_workers', 8))
    
    finally:
        os.unlink(query_config_path)

if __name__ == "__main__":
    main() 