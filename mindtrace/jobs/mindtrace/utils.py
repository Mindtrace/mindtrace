"""
Utility functions and classes for the queue management module.
"""

from typing import Any


def ifnone(val: Any, default: Any) -> Any:
    """Return default if val is None, otherwise return val."""
    return default if val is None else val


class SingletonByArgsMeta(type):
    """
    Metaclass that creates singleton instances based on constructor arguments.
    
    If the same class is instantiated with the same arguments, 
    the same instance will be returned.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        # Create a key based on class name and arguments
        key = (cls.__name__, args, tuple(sorted(kwargs.items())))
        
        if key not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[key] = instance
            
        return cls._instances[key] 