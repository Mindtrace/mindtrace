"""
Core configuration management for Mindtrace project.

Provides centralized configuration with support for directory paths,
environment variables, and JSON file loading/saving.
"""

import os
import json
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DirectoryPaths:
    """Configuration for directory paths."""
    ROOT: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace"))
    LOGS: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace/logs"))
    LIB: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace/lib"))
    DATA: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace/data"))
    MODELS: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace/models"))
    CACHE: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace/cache"))
    TEMP: str = field(default_factory=lambda: os.path.expanduser("~/mindtrace/temp"))


@dataclass
class SourcePaths:
    """Configuration for source code paths."""
    ROOT: str = field(default_factory=lambda: os.getcwd())
    TEST_RESOURCES: str = field(default_factory=lambda: os.path.join(os.getcwd(), "tests", "resources"))


@dataclass
class CoreConfig:
    """Main core configuration container."""
    DIR_PATHS: DirectoryPaths = field(default_factory=DirectoryPaths)
    DIR_SOURCE: SourcePaths = field(default_factory=SourcePaths)


class Config:
    """Core configuration manager for Mindtrace project."""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.getenv("MINDTRACE_CONFIG", "mindtrace_config.json")
        self._config = CoreConfig()
        self._load_config()
    
    def _load_config(self):
        """Load configuration from environment variables and config file."""
        # Load from environment variables first
        self._load_from_env()
        
        # Load from config file if it exists
        if os.path.exists(self.config_file):
            try:
                self._load_from_file(self.config_file)
                logger.info("config_loaded", source="file", file=self.config_file)
            except Exception as e:
                logger.warning("config_load_failed", source="file", file=self.config_file, error=str(e))
        else:
            logger.info("config_file_not_found", file=self.config_file, message="Using default configuration")
    
    def _load_from_env(self):
        """Load configuration from environment variables with MINDTRACE_ prefix."""
        # Directory paths
        if root_dir := os.getenv("MINDTRACE_ROOT_DIR"):
            self._config.DIR_PATHS.ROOT = root_dir
        
        if logs_dir := os.getenv("MINDTRACE_LOGS_DIR"):
            self._config.DIR_PATHS.LOGS = logs_dir
        
        if lib_dir := os.getenv("MINDTRACE_LIB_DIR"):
            self._config.DIR_PATHS.LIB = lib_dir
        
        if data_dir := os.getenv("MINDTRACE_DATA_DIR"):
            self._config.DIR_PATHS.DATA = data_dir
        
        if models_dir := os.getenv("MINDTRACE_MODELS_DIR"):
            self._config.DIR_PATHS.MODELS = models_dir
        
        if cache_dir := os.getenv("MINDTRACE_CACHE_DIR"):
            self._config.DIR_PATHS.CACHE = cache_dir
        
        if temp_dir := os.getenv("MINDTRACE_TEMP_DIR"):
            self._config.DIR_PATHS.TEMP = temp_dir
        
        # Source paths
        if source_root := os.getenv("MINDTRACE_SOURCE_ROOT"):
            self._config.DIR_SOURCE.ROOT = source_root
        
        if test_resources := os.getenv("MINDTRACE_TEST_RESOURCES"):
            self._config.DIR_SOURCE.TEST_RESOURCES = test_resources
    
    def _load_from_file(self, config_file: str):
        """Load configuration from JSON file."""
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Update configuration with file data
        if "DIR_PATHS" in config_data:
            for key, value in config_data["DIR_PATHS"].items():
                if hasattr(self._config.DIR_PATHS, key):
                    setattr(self._config.DIR_PATHS, key, value)
        
        if "DIR_SOURCE" in config_data:
            for key, value in config_data["DIR_SOURCE"].items():
                if hasattr(self._config.DIR_SOURCE, key):
                    setattr(self._config.DIR_SOURCE, key, value)
    
    def save_to_file(self, config_file: Optional[str] = None):
        """Save current configuration to JSON file."""
        file_path = config_file or self.config_file
        config_dict = asdict(self._config)
        
        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        logger.info("config_saved", file=file_path)
    
    def get_config(self) -> CoreConfig:
        """Get current configuration."""
        return self._config
    
    def __getitem__(self, key):
        """Allow dictionary-style access to configuration."""
        if key == "DIR_PATHS":
            return asdict(self._config.DIR_PATHS)
        elif key == "DIR_SOURCE":
            return asdict(self._config.DIR_SOURCE)
        else:
            return getattr(self._config, key, None)


# Global configuration instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
