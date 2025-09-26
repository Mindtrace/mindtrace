import configparser
from pathlib import Path
from typing import Any, Dict

from .paths import expand_tilde_str


def load_ini_as_dict(ini_path: Path) -> Dict[str, Any]:
    """Load and parse an INI file into a nested dictionary with normalized keys.

    - Section names and keys are uppercased for uniform access
    - Values with leading '~' are expanded to the user home directory
    - Returns an empty dict if the file does not exist
    """
    if not ini_path.exists():
        return {}

    parser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    parser.optionxform = str
    parser.read(ini_path)

    result: Dict[str, Any] = {}
    for section in parser.sections():
        # Normalize section name by stripping whitespace and uppercasing
        normalized_section = section.strip().upper()
        result[normalized_section] = {}

        for key, value in parser[section].items():
            # Strip whitespace from key and uppercase
            normalized_key = key.strip().upper()

            # Strip whitespace from value and handle quotes
            stripped_value = value.strip()

            # Remove surrounding quotes if present
            if stripped_value.startswith('"') and stripped_value.endswith('"'):
                stripped_value = stripped_value[1:-1]
            elif stripped_value.startswith("'") and stripped_value.endswith("'"):
                stripped_value = stripped_value[1:-1]

            # Expand tilde and store
            result[normalized_section][normalized_key] = expand_tilde_str(stripped_value)

    return result
