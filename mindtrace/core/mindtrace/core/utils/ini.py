import configparser
from pathlib import Path
from typing import Any, Dict

from mindtrace.core.utils import expand_tilde_str


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
        result[section.upper()] = {
            key.upper(): expand_tilde_str(value) for key, value in parser[section].items()
        }
    return result

