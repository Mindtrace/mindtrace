"""Toolkit system for managing and discovering tools.

This module provides a central registry for discovering and managing toolkits
without using a global registry pattern. Instead, it uses dynamic module inspection
and Python entry points for external package discovery.
"""

import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class ToolMetadata:
    """Metadata for a single tool function."""
    
    name: str
    function: Callable
    description: str
    module: str
    tags: List[str] = field(default_factory=list)
    
    @property
    def is_async(self) -> bool:
        """Check if the tool function is async."""
        return inspect.iscoroutinefunction(self.function)


@dataclass
class ToolkitMetadata:
    """Metadata for a toolkit (collection of tools)."""
    
    name: str
    description: str
    version: str
    tags: List[str] = field(default_factory=list)
    tools: List[ToolMetadata] = field(default_factory=list)
    module_name: str = ""
    
    def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def filter_by_tags(self, tags: Set[str]) -> List[ToolMetadata]:
        """Filter tools by tags."""
        if not tags:
            return self.tools
        return [tool for tool in self.tools if set(tool.tags) & tags]


class ToolkitLoader:
    """Loader for discovering and loading toolkits dynamically.
    
    Supports both built-in toolkits (from mindtrace.agents.tools) and external
    toolkits registered via Python entry points.
    """
    
    def __init__(self, base_package: str = "mindtrace.agents.tools"):
        """Initialize the toolkit loader.
        
        Args:
            base_package: The base package to search for toolkits.
        """
        self.base_package = base_package
        self._cache: Dict[str, ToolkitMetadata] = {}
        self._entry_point_cache: Dict[str, str] = {}  # toolkit_name -> module_path
    
    def discover_toolkits(self) -> List[str]:
        """Discover all available toolkit modules.
        
        Discovers toolkits from:
        1. Built-in toolkits in the base package
        2. External toolkits registered via entry points
        
        Returns:
            List of toolkit module names.
        """
        toolkits = []
        
        # 1. Discover from default package (built-in toolkits)
        try:
            tools_module = importlib.import_module(self.base_package)
            tools_path = Path(tools_module.__file__).parent
            
            for item in tools_path.iterdir():
                if item.is_file() and item.suffix == ".py" and item.stem != "__init__":
                    toolkits.append(item.stem)
                elif item.is_dir() and (item / "__init__.py").exists():
                    toolkits.append(item.name)
        except (ImportError, AttributeError, FileNotFoundError):
            pass
        
        # 2. Discover from entry points (external toolkits)
        entry_point_toolkits = self._discover_from_entry_points()
        toolkits.extend(entry_point_toolkits)
        
        return sorted(set(toolkits))  # Remove duplicates
    
    def _discover_from_entry_points(self) -> List[str]:
        """Discover toolkits registered via entry points.
        
        Returns:
            List of toolkit names discovered from entry points.
        """
        discovered = []
        
        try:
            # Try Python 3.10+ importlib.metadata first
            try:
                from importlib.metadata import entry_points
                toolkit_entry_points = entry_points(group="mindtrace.agents.toolkits")
            except ImportError:
                # Fallback for older Python versions
                try:
                    import pkg_resources
                    toolkit_entry_points = pkg_resources.iter_entry_points("mindtrace.agents.toolkits")
                except ImportError:
                    return []  # Entry points not available
            
            for entry_point in toolkit_entry_points:
                try:
                    # Load the entry point function
                    get_info_func = entry_point.load()
                    
                    # Call it to get toolkit info
                    toolkit_info = get_info_func()
                    
                    toolkit_name = toolkit_info.get("toolkit_name", entry_point.name)
                    module_path = toolkit_info.get("module_path")
                    
                    if module_path:
                        discovered.append(toolkit_name)
                        # Cache the module path for later loading
                        self._entry_point_cache[toolkit_name] = module_path
                        
                except Exception as e:
                    # Silently skip broken entry points
                    continue
                    
        except Exception:
            # Entry points not available or error occurred
            pass
        
        return discovered
    
    def load_toolkit(self, toolkit_name: str, module_path: Optional[str] = None) -> ToolkitMetadata:
        """Load a toolkit and extract its metadata.
        
        Args:
            toolkit_name: The name of the toolkit to load.
            module_path: Optional explicit module path. If None, will try to find
                        the toolkit in the base package or entry point cache.
            
        Returns:
            ToolkitMetadata for the toolkit.
            
        Raises:
            ImportError: If the toolkit cannot be imported.
            ValueError: If the toolkit is missing required metadata.
        """
        if toolkit_name in self._cache:
            return self._cache[toolkit_name]
        
        # Determine module path
        if module_path:
            module_name = module_path
        elif toolkit_name in self._entry_point_cache:
            # Load from entry point
            module_name = self._entry_point_cache[toolkit_name]
        else:
            # Load from default package
            module_name = f"{self.base_package}.{toolkit_name}"
        
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise ImportError(f"Failed to import toolkit '{toolkit_name}' from '{module_name}': {e}")
        
        # Extract toolkit metadata from module attributes
        name = getattr(module, "__toolkit_name__", toolkit_name)
        description = getattr(module, "__toolkit_description__", module.__doc__ or "")
        version = getattr(module, "__toolkit_version__", "0.0.0")
        tags = getattr(module, "__toolkit_tags__", [])
        
        # Extract all callable tools from the module
        tools = []
        all_exports = getattr(module, "__all__", [])
        
        for attr_name in all_exports:
            attr = getattr(module, attr_name, None)
            if callable(attr) and not attr_name.startswith("_"):
                # Extract docstring as description
                doc = inspect.getdoc(attr) or ""
                tool_tags = list(tags)  # Inherit toolkit tags
                
                tool_metadata = ToolMetadata(
                    name=attr_name,
                    function=attr,
                    description=doc,
                    module=module_name,
                    tags=tool_tags,
                )
                tools.append(tool_metadata)
        
        toolkit_metadata = ToolkitMetadata(
            name=name,
            description=description,
            version=version,
            tags=tags,
            tools=tools,
            module_name=module_name,
        )
        
        self._cache[toolkit_name] = toolkit_metadata
        return toolkit_metadata
    
    def load_all_toolkits(self) -> List[ToolkitMetadata]:
        """Load all discovered toolkits.
        
        Returns:
            List of all toolkit metadata.
        """
        toolkits = []
        for toolkit_name in self.discover_toolkits():
            try:
                toolkit = self.load_toolkit(toolkit_name)
                toolkits.append(toolkit)
            except (ImportError, ValueError) as e:
                # Log error but continue with other toolkits
                print(f"Warning: Failed to load toolkit '{toolkit_name}': {e}")
        return toolkits
    
    def get_toolkit(self, toolkit_name: str) -> Optional[ToolkitMetadata]:
        """Get a specific toolkit by name.
        
        Args:
            toolkit_name: The name of the toolkit.
            
        Returns:
            ToolkitMetadata if found, None otherwise.
        """
        try:
            return self.load_toolkit(toolkit_name)
        except (ImportError, ValueError):
            return None
    
    def list_toolkits(self) -> Dict[str, str]:
        """List all available toolkits with their descriptions.
        
        Returns:
            Dictionary mapping toolkit names to descriptions.
        """
        result = {}
        for toolkit_name in self.discover_toolkits():
            try:
                toolkit = self.load_toolkit(toolkit_name)
                result[toolkit_name] = toolkit.description
            except (ImportError, ValueError) as e:
                result[toolkit_name] = f"Error: {e}"
        return result
    
    def get_toolkit_source(self, toolkit_name: str) -> str:
        """Get the source of a toolkit (built-in or external).
        
        Args:
            toolkit_name: The name of the toolkit.
            
        Returns:
            "built-in" if from default package, "external" if from entry point,
            "unknown" otherwise.
        """
        if toolkit_name in self._entry_point_cache:
            return "external"
        elif toolkit_name in self._cache or f"{self.base_package}.{toolkit_name}" in [t.module_name for t in self._cache.values()]:
            return "built-in"
        else:
            # Try to determine by attempting discovery
            if toolkit_name in self._discover_from_entry_points():
                return "external"
            return "built-in"
    
    def clear_cache(self):
        """Clear the toolkit cache."""
        self._cache.clear()


# Convenience function for getting the default loader
_default_loader: Optional[ToolkitLoader] = None


def get_loader() -> ToolkitLoader:
    """Get the default toolkit loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = ToolkitLoader()
    return _default_loader


def discover_toolkits() -> List[str]:
    """Discover all available toolkits."""
    return get_loader().discover_toolkits()


def load_toolkit(toolkit_name: str) -> ToolkitMetadata:
    """Load a specific toolkit."""
    return get_loader().load_toolkit(toolkit_name)


def list_toolkits() -> Dict[str, str]:
    """List all available toolkits."""
    return get_loader().list_toolkits()

