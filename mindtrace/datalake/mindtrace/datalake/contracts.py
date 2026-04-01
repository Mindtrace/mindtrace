import pathlib
from typing import Any

from datasets import Image, List, Sequence, Value

contracts_to_hf_type = {
    "image": Image(),
    "classification": {"label": Value("string"), "confidence": Value("float")},
    "bbox": {"bbox": List(Sequence(Value("float"), length=4))},
}


def validate_contract(data: Any, contract: str):
    if contract == "default":
        pass
    elif contract == "image":
        if not isinstance(data, (pathlib.Path, pathlib.PosixPath)):
            raise ValueError(f"Data must be a path to an image, got {type(data)}")
        # TODO: check if this is actually an image
    elif contract == "classification":
        if not isinstance(data, dict):
            raise ValueError(f"Data must be a dictionary, got {type(data)}")
        if "label" not in data:
            raise ValueError("Data must contain a 'label' key")
        if "confidence" not in data:
            raise ValueError("Data must contain a 'confidence' key")
        if not isinstance(data["confidence"], float):
            raise ValueError(f"Confidence must be a float, got {type(data['confidence'])}")
        if data["confidence"] < 0 or data["confidence"] > 1:
            raise ValueError("Confidence must be between 0 and 1")
    elif contract == "bbox":
        if not isinstance(data, dict):
            raise ValueError(f"Data must be a dictionary, got {type(data)}")
        if "bbox" not in data:
            raise ValueError("Data must contain a 'bbox' key")
        if not isinstance(data["bbox"], list):
            raise ValueError(f"Bbox must be a list, got {type(data['bbox'])}")

        for entry in data["bbox"]:
            if not isinstance(entry, list):
                raise ValueError(f"Bbox must be a list of lists, got {type(entry)}")
            if len(entry) != 4:
                raise ValueError("Bbox must be a list of lists of 4 elements")
            if not all(isinstance(x, float) for x in entry):
                raise ValueError("Bbox must be a list of lists of floats")
            # Validate coordinates are non-negative (x1, y1, x2, y2 format)
            if entry[0] < 0 or entry[1] < 0 or entry[2] < 0 or entry[3] < 0:
                raise ValueError("Bbox coordinates must be non-negative")
            # Validate that x2 >= x1 and y2 >= y1
            if entry[2] < entry[0] or entry[3] < entry[1]:
                raise ValueError("Bbox must have x2 >= x1 and y2 >= y1")
    elif contract == "regression":
        pass
    elif contract == "segmentation":
        pass
    else:
        raise ValueError(f"Unsupported contract: {contract}")
