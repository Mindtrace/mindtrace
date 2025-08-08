import argparse
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import os
from dotenv import load_dotenv
import tempfile
import pandas as pd
from enum import Enum

from mindtrace.automation.database.database_connection import DatabaseConnection
from mindtrace.storage.gcs import GCSStorageHandler
from mindtrace.automation.label_studio.label_studio_api import LabelStudio, LabelStudioConfig

# Load environment variables from .env file
load_dotenv("envs/database.env")

class QueryType(Enum):
    """Supported database query types."""
    GET_IMAGES_BY_DATE = "get_images_by_date"
    GET_IMAGES_BY_CAMERA = "get_images_by_camera"
    GET_IMAGES_BY_TIMESTAMP = "get_images_by_timestamp"
    GET_IMAGES_BY_SERIAL_NUMBER = "get_images_by_serial_number"

class QueryManager:
    """Manages predefined database queries."""
    
    QUERIES = {
        QueryType.GET_IMAGES_BY_DATE: """
            SELECT 
                img."bucketName",
                img."fullPath",
                img."name" AS "image_name",
                analytics."createdAt" AS "entry_date"
            FROM public."AdientImage" AS img
            JOIN public."AdientAnalytics" AS analytics 
                ON analytics."id" = img."analyticsId"
            WHERE analytics."createdAt" >= %s 
            AND analytics."createdAt" < %s
        """,
        QueryType.GET_IMAGES_BY_SERIAL_NUMBER: """
            SELECT 
                img."bucketName",
                img."fullPath",
                img."name" AS "image_name",
                analytics."createdAt" AS "entry_date"
            FROM public."AdientImage" AS img
            JOIN public."AdientAnalytics" AS analytics 
                ON analytics."id" = img."analyticsId"
            WHERE left(img."name", 7) = 'Basler:'
            AND EXISTS (
                SELECT 1
                FROM unnest(%s::text[]) AS pat(p)
                WHERE analytics."partId" ILIKE pat.p
            )
        """
    }
    
    @classmethod
    def get_query(cls, query_type: str) -> str:
        """Get SQL query by type."""
        try:
            query_enum = QueryType(query_type)
            return cls.QUERIES[query_enum]
        except ValueError:
            raise ValueError(f"Unknown query type: {query_type}. Available types: {[qt.value for qt in QueryType]}")
        except KeyError:
            # Query types that are handled procedurally (e.g., serial number) won't have a static SQL here
            return None
    
    @classmethod
    def get_available_queries(cls) -> list:
        """Get list of available query types."""
        return [qt.value for qt in QueryType]

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
        self.query_type = self.config.get('database_queries', {}).get('query_type')
        
        # Get query type from config
        query_config = self.config.get('database_queries', {})
        if not query_config:
            raise ValueError("No database_queries section found in config file")
        
        query_type = query_config.get('query_type')
        if not query_type:
            raise ValueError("No query_type specified in database_queries section")
        
        # Get the actual SQL query where applicable
        sql_query = QueryManager.get_query(query_type)
        
        # Create query config for database connection
        db_query_config = {}
        if sql_query:
            if query_type == QueryType.GET_IMAGES_BY_DATE.value:
                db_query_config['get_images_by_date'] = sql_query
            elif query_type == QueryType.GET_IMAGES_BY_SERIAL_NUMBER.value:
                db_query_config['get_images_by_serial_number'] = sql_query
        
        self.db_conn = DatabaseConnection(
            database=database,
            user=user,
            password=password,
            host=host,
            port=int(port),
            query_config=db_query_config
        )
        
        self.gcp_manager = GCSStorageHandler(
            bucket_name=gcp_bucket,
            credentials_path=gcp_credentials_path
        )
        
        # Create timestamped subdirectory within the parent download path
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.local_download_path = Path(local_download_path) / timestamp
        self.local_download_path.mkdir(parents=True, exist_ok=True)
        
        print(f"Created download directory: {self.local_download_path}")
        
        # Store the parent path for reference
        self.parent_download_path = Path(local_download_path)
        
        # Initialize Label Studio client if configured
        self.label_studio = None
        if 'label_studio' in config:
            label_studio_config = config['label_studio']
            if 'api' in label_studio_config:
                api_config = label_studio_config['api']
                self.label_studio = LabelStudio(
                    LabelStudioConfig(
                        url=api_config['url'],
                        api_key=api_config['api_key'],
                        gcp_creds=api_config.get('gcp_credentials_path')
                    )
                )

    def _read_serial_numbers_from_file(self, file_path: str) -> list:
        """Read serial numbers from a text file (one per line)."""
        try:
            with open(file_path, 'r') as f:
                lines = [line.strip() for line in f.readlines()]
                return [ln for ln in lines if ln and not ln.startswith('#')]
        except Exception as e:
            print(f"Warning: Failed to read serial numbers from {file_path}: {e}")
            return []

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
        # If not configured, return None to signal no sampling
        return None

    def filter_existing_label_studio_images(self, df: pd.DataFrame, project_title_prefix: Optional[str] = None) -> pd.DataFrame:
        """Filter out images that already exist in Label Studio projects.
        
        Args:
            df: DataFrame with image data
            project_title_prefix: Optional prefix to filter Label Studio projects
            
        Returns:
            DataFrame with existing images removed
        """
        if self.label_studio is None:
            print("Label Studio not configured, skipping deduplication")
            return df
        
        if df.empty:
            return df
        
        print("Checking for existing images in Label Studio projects...")
        
        try:
            existing_gcs_paths = self.label_studio.get_all_existing_gcs_paths(project_title_prefix)
            print(f"Found {len(existing_gcs_paths)} existing GCS paths in Label Studio")
            
            if not existing_gcs_paths:
                print("No existing images found in Label Studio")
                return df
            
            df_gcs_paths = set(df['ImgPath'].tolist())
            
            bucket_name = self.config.get('gcp', {}).get('data_bucket', '')
            bucket_prefix = f"gs://{bucket_name}/"
            
            normalized_ls_paths = set()
            for path in existing_gcs_paths:
                if path.startswith(bucket_prefix):
                    normalized_path = path[len(bucket_prefix):]
                    normalized_ls_paths.add(normalized_path)
                else:
                    normalized_ls_paths.add(path)
            
            overlapping_paths = df_gcs_paths.intersection(normalized_ls_paths)
            
            if overlapping_paths:
                print(f"Found {len(overlapping_paths)} images already in Label Studio projects")
                
                df_filtered = df[~df['ImgPath'].isin(overlapping_paths)]
                filtered_count = len(df) - len(df_filtered)
                print(f"\nDEDUPLICATION SUMMARY:")
                print(f"  Total images found: {len(df)}")
                print(f"  Images already in Label Studio: {filtered_count}")
                print(f"  Images remaining for download: {len(df_filtered)}")
                

                
                return df_filtered
            else:
                print("No overlapping images found")
                return df
                
        except Exception as e:
            print(f"Warning: Error checking Label Studio for existing images: {e}")
            print("Continuing without deduplication...")
            return df

    def check_sufficient_images(self, df: pd.DataFrame, cameras: Dict[str, dict]) -> Dict[str, dict]:
        """Check if we have sufficient unused images for each camera.
        
        Args:
            df: DataFrame with available images after Label Studio filtering
            cameras: Original camera configuration with requested numbers
            
        Returns:
            Dictionary with availability status for each camera
        """
        availability = {}
        
        for camera, config in cameras.items():
            camera_df = df[df['Camera'] == camera]
            available_count = len(camera_df)
            
            requested_count = None
            if 'number' in config:
                requested_count = config['number']
            elif 'proportion' in config:
                pass
            
            if requested_count is not None:
                sufficient = available_count >= requested_count
                availability[camera] = {
                    'requested': requested_count,
                    'available': available_count,
                    'sufficient': sufficient,
                    'shortfall': max(0, requested_count - available_count)
                }
            else:
                availability[camera] = {
                    'requested': 'proportion-based',
                    'available': available_count,
                    'sufficient': True,
                    'shortfall': 0
                }
        
        return availability

    def apply_camera_sampling(
        self,
        df: pd.DataFrame,
        cameras: Dict[str, dict],
        seed: Optional[int] = None
    ) -> pd.DataFrame:
        if df.empty:
            return df

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
                    has_proportion = 'proportion' in config
                    has_number = 'number' in config
                    
                    if has_proportion and has_number:
                        print(f"Warning: Both proportion and number specified for camera {camera}. Using number.")
                    
                    if has_number:
                        n_samples = min(config['number'], len(camera_df))
                        print(f"Camera {camera}: {len(camera_df)} available, taking {n_samples} (requested: {config['number']})")
                    elif has_proportion:
                        n_samples = int(total_available * config['proportion'])
                        print(f"Camera {camera}: {len(camera_df)} available, taking {n_samples} ({config['proportion']*100:.1f}%)")
                    else:
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

    def get_images_by_date(
        self,
        start_date: str,
        end_date: str,
        cameras: Optional[Dict[str, dict]] = None,
        number_samples_per_day: Optional[int] = None,
        seed: Optional[int] = None
    ) -> pd.DataFrame:
        df = self.db_conn.get_images_by_date(
            start_timestamp=start_date,
            end_timestamp=end_date,
            number_samples_per_day=number_samples_per_day
        )

        if seed is not None:
            import random
            random.seed(seed)
            print(f"Using random seed: {seed}")

        if df.empty:
            print("No images found in the specified date range")
            return df

        print(f"Found {len(df)} total images in date range {start_date} to {end_date}")

        return df

    def get_images_by_serial_numbers(self, serial_numbers: list) -> pd.DataFrame:
        """Fetch images filtered by Basler serial numbers."""
        df = self.db_conn.get_basler_images_by_serial_numbers(serial_numbers)
        if df.empty:
            print("No images found for provided serial numbers")
            return df
        print(f"Found {len(df)} total images for {len(serial_numbers)} serial numbers")
        return df

    def download_images(self, df: pd.DataFrame, max_workers: int = 8) -> Dict[str, str]:
        """Download images from GCS using paths from database.
        
        Returns:
            Dictionary mapping local filenames to GCS paths
        """
        if df.empty:
            print("No images to download")
            return {}
        
        gcs_path_mapping = {
            "bucket": self.gcp_manager.bucket_name,
            "prefix": "",
            "files": {}
        }
            
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
                
                gcs_path_mapping["files"][filename] = row['ImgPath']
            
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
        
        return gcs_path_mapping
    
    def get_data_with_gcs_paths(self) -> Dict[str, str]:
        try:
            is_serial_mode = self.query_type == QueryType.GET_IMAGES_BY_SERIAL_NUMBER.value

            if is_serial_mode:
                cameras = None  # Skip sampling in serial-number mode
                print("Serial-number mode: skipping camera sampling")
                serial_numbers = self.config.get('serial_numbers')
                if not serial_numbers and self.config.get('serial_numbers_file'):
                    serial_numbers = self._read_serial_numbers_from_file(self.config['serial_numbers_file'])
                if not serial_numbers:
                    print("No serial numbers provided. Nothing to fetch.")
                    return {}
                df = self.get_images_by_serial_numbers(serial_numbers)
            else:
                cameras = self.get_camera_proportions(self.config)
                df = self.get_images_by_date(
                    start_date=self.config['start_date'],
                    end_date=self.config['end_date'],
                    cameras=None,
                    number_samples_per_day=self.config.get('samples_per_day'),
                    seed=self.config.get('seed')
                )
                project_prefix = self.config.get('label_studio', {}).get('project', {}).get('title')
                df = self.filter_existing_label_studio_images(df, project_prefix)
             
            df = self.apply_camera_sampling(df, cameras, seed=self.config.get('seed'))
            
            os.makedirs('database_data', exist_ok=True)
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            df.to_csv(f'database_data/{timestamp}.csv')
            
            gcs_path_mapping = self.download_images(df, max_workers=self.config.get('max_workers', 8))
            return gcs_path_mapping
            
        except Exception as e:
            print(f"Error: {e}")
            raise e
    
    def get_data(self):       
        try:
            is_serial_mode = self.query_type == QueryType.GET_IMAGES_BY_SERIAL_NUMBER.value

            if is_serial_mode:
                cameras = None  # Skip sampling in serial-number mode
                print("Serial-number mode: skipping camera sampling")
                serial_numbers = self.config.get('serial_numbers')
                if not serial_numbers and self.config.get('serial_numbers_file'):
                    serial_numbers = self._read_serial_numbers_from_file(self.config['serial_numbers_file'])
                if not serial_numbers:
                    print("No serial numbers provided. Nothing to fetch.")
                    return
                df = self.get_images_by_serial_numbers(serial_numbers)
            else:
                cameras = self.get_camera_proportions(self.config)
                df = self.get_images_by_date(
                    start_date=self.config['start_date'],
                    end_date=self.config['end_date'],
                    cameras=None,
                    number_samples_per_day=self.config.get('samples_per_day'),
                    seed=self.config.get('seed')
                )
                project_prefix = self.config.get('label_studio', {}).get('project', {}).get('title')
                df = self.filter_existing_label_studio_images(df, project_prefix)
             
            df = self.apply_camera_sampling(df, cameras, seed=self.config.get('seed'))
            
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