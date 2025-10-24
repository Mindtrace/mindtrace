import json
import os
import re
from typing import Any, Dict, List, Optional

from mindtrace.automation.label_studio.label_studio_api import LabelStudio
from mindtrace.core import Mindtrace


class GenerateIdConfig(Mindtrace):
    """Generate camera-based feature detection configuration from Label Studio annotations.

    This class processes a single Label Studio project export containing one image per camera.
    It extracts camera names from image filenames, groups annotations by camera, and outputs
    a configuration compatible with FeatureDetector.

    Expected workflow:
    1. Create Label Studio project with one representative image per camera
    2. Annotate features with labels like: feature_1, feature_2, item_A (no camera prefix)
    3. Export project as JSON
    4. Use build_camera_config_from_project() to generate config
    5. Use resulting config with FeatureDetector for prediction validation
    """

    def __init__(self, label_studio: LabelStudio = None, label_separator: str = "_", **kwargs):
        """Initialize the config generator.

        Args:
            label_studio: Label Studio API instance (optional, only needed for export)
            label_separator: Character(s) used to separate label prefix from ID (default: "_")
            **kwargs: Additional arguments passed to Mindtrace base class
        """
        super().__init__(**kwargs)
        self.label_studio = label_studio
        self.label_separator = label_separator

    def _extract_camera_from_image_path(self, image_path: str) -> Optional[str]:
        """Extract camera identifier from image path.

        Handles both GCP synced paths (gs://...) and local uploaded paths (/data/upload/...).
        Tries to match pattern 'camX' where X is a number. If no match,
        returns the filename without extension.

        Args:
            image_path: Image path or URL
                - GCP: 'gs://bucket/path/cam1_image.jpg'
                - Local: '/data/upload/1/cam1_image.jpg'
                - Presigned URL: 'http://host/api/presign/?fileuri=gs://...'

        Returns:
            Camera identifier (e.g., 'cam1') or None if path is invalid
        """
        if not image_path:
            return None

        # Extract filename from path (works for both local and GCS paths)
        filename = image_path.split("/")[-1]

        # Try to match camX pattern (case insensitive)
        match = re.search(r"cam(\d+)", filename, re.IGNORECASE)
        if match:
            return f"cam{match.group(1)}"

        # Fallback: use filename without extension
        return filename.rsplit(".", 1)[0] if "." in filename else filename

    def export_project(self, project_name: str, export_path: str) -> str:
        """Export a single Label Studio project to JSON.

        Args:
            project_name: Name of the Label Studio project
            export_path: Path where the export JSON will be saved

        Returns:
            Path to the exported JSON file

        Raises:
            ValueError: If label_studio instance is not provided
            RuntimeError: If export fails
        """
        if self.label_studio is None:
            raise ValueError("LabelStudio instance required for export. Provide it in __init__")

        export_dir = os.path.dirname(export_path)
        if export_dir and not os.path.exists(export_dir):
            self.logger.info(f"Creating directory {export_dir}")
            os.makedirs(export_dir, exist_ok=True)

        try:
            self.label_studio.export_annotations(
                project_name=project_name, export_location=export_path, export_type="JSON"
            )
            self.logger.info(f"Exported project '{project_name}' to {export_path}")
            return export_path
        except Exception as e:
            raise RuntimeError(f"Failed to export project '{project_name}': {e}") from e

    def build_camera_config_from_project(
        self,
        export_path: str,
        output_path: str,
    ) -> Dict[str, Any]:
        """Build camera-keyed feature detection config from a single Label Studio project export.

        Processes a Label Studio JSON export containing one image per camera. Extracts camera
        names from image filenames, groups annotations by camera, and outputs a configuration
        compatible with FeatureDetector.

        Args:
            export_path: Path to Label Studio JSON export file
            output_path: Path to write the generated config JSON

        Returns:
            The generated configuration dictionary in FeatureDetector format:
            {
                "camera_id": {
                    "features": {
                        "feature_id": {
                            "label": "feature_type",
                            "bbox": [x1, y1, x2, y2],
                            "expected_count": 1,
                            "params": {"class_id": 0}
                        }
                    }
                }
            }

        Raises:
            ValueError: If export_path doesn't exist or is invalid
            RuntimeError: If config generation fails
        """
        if not os.path.isfile(export_path):
            raise ValueError(f"Export file does not exist: {export_path}")

        try:
            with open(export_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to read export file {export_path}: {e}") from e

        # Structure: {camera_id: {label: [feature_objects]}}
        camera_data: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        global_labels: set[str] = set()

        for task in data:
            # Extract image path from task data
            image_path = None
            if "data" in task and isinstance(task["data"], dict):
                image_path = task["data"].get("image")

            if not image_path:
                self.logger.warning("Task missing image path, skipping")
                continue

            # Extract camera identifier
            camera_id = self._extract_camera_from_image_path(image_path)
            if not camera_id:
                self.logger.warning(f"Could not extract camera from path: {image_path}")
                continue

            # Process annotations
            annotations = task.get("annotations", [])
            for ann in annotations:
                results = ann.get("result", [])
                for res in results:
                    if res.get("type") != "rectanglelabels":
                        continue

                    value = res.get("value", {})
                    labels = value.get("rectanglelabels", [])
                    if not labels:
                        continue

                    label_str = labels[0]

                    # Parse label using configurable separator
                    if self.label_separator not in label_str:
                        self.logger.warning(f"Label '{label_str}' missing '{self.label_separator}' separator; skipping")
                        continue

                    parts = label_str.split(self.label_separator, 1)
                    if len(parts) != 2:
                        self.logger.warning(f"Label '{label_str}' invalid format; skipping")
                        continue

                    label_prefix, feature_id = parts
                    if not feature_id:
                        self.logger.warning(f"Label '{label_str}' has empty ID part; skipping")
                        continue

                    label_lower = label_prefix.lower()
                    global_labels.add(label_lower)

                    # Get image dimensions from result (Label Studio stores them here)
                    # or fallback to task data
                    original_width = res.get("original_width") or task.get("data", {}).get("width")
                    original_height = res.get("original_height") or task.get("data", {}).get("height")

                    # Convert Label Studio percentage coords to pixel coords
                    x_pct = value.get("x", 0)
                    y_pct = value.get("y", 0)
                    width_pct = value.get("width", 0)
                    height_pct = value.get("height", 0)

                    if original_width and original_height:
                        x1 = int(x_pct * original_width / 100)
                        y1 = int(y_pct * original_height / 100)
                        x2 = int((x_pct + width_pct) * original_width / 100)
                        y2 = int((y_pct + height_pct) * original_height / 100)
                        bbox = [x1, y1, x2, y2]
                    else:
                        # Store as percentage if dimensions not available
                        self.logger.warning(
                            f"Image dimensions not available for {image_path}, storing bbox as percentages"
                        )
                        bbox = [x_pct, y_pct, x_pct + width_pct, y_pct + height_pct]

                    item = {
                        "id": str(feature_id),
                        "class_id": None,
                        "label": label_lower,
                        "bbox": bbox,
                    }

                    camera_data.setdefault(camera_id, {}).setdefault(label_lower, []).append(item)

        # Assign global class IDs based on unique labels
        label_to_class: Dict[str, int] = {lbl: idx for idx, lbl in enumerate(sorted(global_labels))}

        # Convert to FeatureDetector format
        config: Dict[str, Any] = {}
        for camera_id, label_groups in camera_data.items():
            features: Dict[str, Dict[str, Any]] = {}

            for label, items in label_groups.items():
                class_id = label_to_class.get(label)

                for item in items:
                    feature_id = item["id"]
                    full_feature_id = f"{label}_{feature_id}"

                    features[full_feature_id] = {
                        "label": label,
                        "bbox": item["bbox"],
                        "expected_count": 1,
                        "params": {"class_id": class_id},
                    }

            config[camera_id] = {"features": features}

        # Write output
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)

        self.logger.info(f"Generated camera-based config for {len(config)} cameras")
        self.logger.info(f"Wrote config to {output_path}")

        return config
