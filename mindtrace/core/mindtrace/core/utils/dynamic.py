"""Utility methods relating to dynamically generating objects."""

import importlib
from typing import Any


def dynamic_instantiation(module_name: str, class_name: str, **kwargs) -> Any:
    """Dynamically instantiates a class from a module."""
    module = importlib.import_module(module_name)
    class_ = getattr(module, class_name)
    instance = class_(**kwargs)
    return instance


def instantiate_target(target: str, **kwargs) -> Any:
    """Instantiates a target object from a string.

    The target string should be in the same format as expected from Hydra targets. I.e. 'module_name.class_name'.

    Args:
        target: A string representing a target object.

    Example::

        from mindtrace.core import instantiate_target

        target = 'mindtrace.core.config.Config'
        config = instantiate_target(target)

        print(type(config))  # <class 'mindtrace.core.config.Config'>
    """
    module_name, class_name = target.rsplit(".", 1)
    return dynamic_instantiation(module_name, class_name, **kwargs)


def get_class(target: str) -> type:
    """Gets a class from a module path string without instantiating it.

    The target string should be in the same format as expected from Hydra targets. I.e. 'module_name.class_name'.

    Args:
        target: A string representing a target class path.

    Returns:
        The class object.

    Example::

        from mindtrace.core import get_class

        target = 'mindtrace.core.config.Config'
        config_class = get_class(target)

        print(config_class)  # <class 'mindtrace.core.config.Config'>
    """
    module_name, class_name = target.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)
