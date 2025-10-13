import json
import os
from typing import Any, Dict, List

from mindtrace.core import Mindtrace
from mindtrace.automation.label_studio.label_studio_api import LabelStudio

class GenerateIdConfig(Mindtrace):
    """Generate feature detection configuration from Label Studio annotations.
    
    This class exports Label Studio projects and converts annotations into
    a generic feature detection configuration format.
    """
    
    def __init__(self, label_studio: LabelStudio, label_separator: str = "_", **kwargs):
        """Initialize the config generator.
        
        Args:
            label_studio: Label Studio API instance
            label_separator: Character(s) used to separate label prefix from ID (default: "_")
            **kwargs: Additional arguments passed to Mindtrace base class
        """
        super().__init__(**kwargs)
        self.label_studio = label_studio
        self.label_separator = label_separator

    def export_projects(self, save_path: str, project_names: List[str]=None, project_prefix: str=None):
        if project_names and project_prefix:
            raise ValueError("Provide only one of project_names or project_prefix, not both")
        if project_names is None and project_prefix is None:
            raise ValueError("Either project_names or project_prefix must be provided")
        if not os.path.exists(save_path):
            self.logger.info(f"Creating directory {save_path}")
            os.makedirs(save_path,exist_ok=True)
        if project_prefix is not None:
            return self.label_studio.export_projects_by_prefix(
                project_name_prefix=project_prefix,
                output_dir=save_path,
                export_type="JSON",
                download_resources=True,
            )
        successful_projects = []
        if project_names is not None:
            for project_name in project_names:
                try:
                    project_dir = os.path.join(save_path, project_name)
                    os.makedirs(project_dir, exist_ok=True)
                    export_file = os.path.join(project_dir, "export.json")
                    _ = self.label_studio.export_annotations(
                        project_name=project_name,
                        export_location=export_file,
                        export_type="JSON"
                    )
                    successful_projects.append(project_name)
                except Exception as e:
                    self.logger.error(f"Failed to export annotations for project {project_name}: {e}")
        for name in project_names:
            if name not in successful_projects:
                self.logger.warning(f"Project {name} export failed or was not found")
        return successful_projects

    def build_id_config_from_exports(
        self,
        exports_root: str,
        output_path: str,
    ) -> Dict[str, Any]:
        """Build feature detection config from exported Label Studio annotations.
        
        Args:
            exports_root: Directory containing exported project folders
            output_path: Path to write the generated config JSON
            
        Returns:
            The generated configuration dictionary
        """
        if not os.path.isdir(exports_root):
            raise ValueError(f"exports_root does not exist or is not a directory: {exports_root}")

        combined: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        global_labels: set[str] = set()

        for entry in sorted(os.listdir(exports_root)):
            project_dir = os.path.join(exports_root, entry)
            if not os.path.isdir(project_dir):
                continue
            export_file = os.path.join(project_dir, "export.json")
            if not os.path.isfile(export_file):
                self.logger.warning(f"Missing export.json in {project_dir}, skipping")
                continue

            try:
                with open(export_file, "r") as f:
                    data = json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to read {export_file}: {e}")
                continue

            groups: Dict[str, List[Dict[str, Any]]] = {}

            for task in data:
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
                            self.logger.warning(
                                f"Label '{label_str}' missing '{self.label_separator}' separator; skipping"
                            )
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
                        
                        bbox = [
                            value.get("x"),
                            value.get("y"),
                            value.get("width"),
                            value.get("height"),
                        ]
                        item = {
                            "id": str(feature_id),
                            "class_id": None,
                            "label": label_lower,
                            "name": label_str,
                            "bbox": bbox,
                        }
                        groups.setdefault(label_lower, []).append(item)

            if groups:
                combined[entry] = groups

        # Assign class IDs based on unique labels
        label_to_class: Dict[str, int] = {lbl: idx for idx, lbl in enumerate(sorted(global_labels))}
        for project_groups in combined.values():
            for label, items in project_groups.items():
                class_id = label_to_class.get(label)
                for obj in items:
                    obj["class_id"] = class_id

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(combined, f, indent=2)
        self.logger.info(f"Wrote ID config to {output_path}")
        return combined
        
            

                
                
        
