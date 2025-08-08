import pandas as pd
from datetime import datetime, timedelta, date
import psycopg2
import yaml
import os
from typing import Dict, Optional

class DatabaseConnection:
    def __init__(
        self, 
        database: str, 
        user: str, 
        password: str, 
        host: str, 
        port: int,
        query_config: Dict[str, str]
    ):
        """Initialize database connection."""
        self.conn_params = {
            'dbname': database,
            'host': host,
            'user': user,
            'password': password,
            'port': port
        }
        
        # Load query configuration
        self.query_config = query_config
        # self.query_config = self._load_query_config(query_config_path)
        
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            self.cursor = self.conn.cursor()
            print('Connected to the database')
        except Exception as e:
            print(f"Failed to connect to database: {e}")
            self.conn = None
            self.cursor = None
    
    def _load_query_config(self, config_path: str = None) -> dict:
        """Load SQL queries from config file."""
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'database_queries.yaml')
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    print(f"Loaded queries from {config_path}")
                    return config
            else:
                raise FileNotFoundError(f"Query config file not found at {config_path}")
        except Exception as e:
            raise Exception(f"Error loading query config: {e}")
    
    def __del__(self):
        """Clean up database connections."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def get_images_by_date(
        self,
        start_timestamp: str,
        end_timestamp: str,
        number_samples_per_day: int = None
    ) -> pd.DataFrame:
        """Get image metadata from database within date range.
        
        Args:
            start_timestamp: Start date in YYYY-MM-DD format
            end_timestamp: End date in YYYY-MM-DD format
            number_samples_per_day: Optional number of samples to take per day
            
        Returns:
            DataFrame with image metadata including paths and camera info
        """
        # Convert end_timestamp to next day to include the full end date
        if isinstance(end_timestamp, str):
            end_timestamp = datetime.strptime(end_timestamp, "%Y-%m-%d")
        end_timestamp = end_timestamp + timedelta(days=1)

        # Get query from config
        query = self.query_config.get('get_images_by_date')
        
        try:
            self.cursor.execute(query, (start_timestamp, end_timestamp))
            results = self.cursor.fetchall()
            
            # Convert to DataFrame
            df = pd.DataFrame(results, columns=[
                'BucketName', 'ImgPath', 'ImgName', 'EntryDate'
            ])
            
            # Extract camera from image name
            df['Camera'] = df['ImgName'].apply(lambda x: x.split('-')[0])
            
            if number_samples_per_day is not None and not df.empty:
                # Create date column for grouping
                df['Date'] = pd.to_datetime(df['EntryDate']).dt.date
                
                # Sample per day
                sampled_df = df.groupby('Date').apply(
                    lambda x: x.sample(
                        n=min(len(x), number_samples_per_day)
                    )
                ).reset_index(drop=True)
                
                # Drop temporary date column
                sampled_df = sampled_df.drop('Date', axis=1)
                return sampled_df
            
            return df
            
        except Exception as e:
            print(f"Error querying database: {e}")
            return pd.DataFrame()

    def get_basler_images_by_serial_numbers(self, serial_numbers: list) -> pd.DataFrame:
        """Get Basler image metadata from database for specific serial numbers.
        
        Args:
            serial_numbers: List of serial number substrings to match against analytics.partId
        
        Returns:
            DataFrame with image metadata including paths and camera info
        """
        if not serial_numbers:
            return pd.DataFrame()

        # Build array of wildcard patterns for EXISTS + unnest
        patterns = [f"%{sn}%" for sn in serial_numbers]

        # Get query from config (symmetry with get_images_by_date)
        query = self.query_config.get('get_images_by_serial_number')
        if not query:
            print("Error: get_images_by_serial_number query not configured")
            return pd.DataFrame()

        try:
            # Pass patterns as a single array parameter
            self.cursor.execute(query, (patterns,))
            results = self.cursor.fetchall()

            df = pd.DataFrame(results, columns=[
                'BucketName', 'ImgPath', 'ImgName', 'EntryDate'
            ])
            
            # Ensure ImgName column is string before split
            df['ImgName'] = df['ImgName'].astype(str)
            # Extract camera from image name (e.g., 'Basler:cam1-...' -> 'Basler:cam1')
            df['Camera'] = df['ImgName'].apply(lambda x: x.split('-')[0] if '-' in x else x)
            return df
        except Exception as e:
            print(f"Error querying database by serial numbers: {e}")
            return pd.DataFrame()
    