from mindtrace.automation.label_studio.label_studio_api import LabelStudio
from mindtrace.core import Mindtrace
from typing import List
import os
class GenerateIdConfig(Mindtrace):
    def __init__(self, label_studio: LabelStudio, **kwargs):
        super().__init__(**kwargs)
        self.label_studio = label_studio

    def export_projects(self, save_path: str, project_names: List[str]=None, project_prefix: str=None):
        if project_names and project_prefix:
            raise ValueError("Either project_names or project_prefix must be provided")
        if not os.path.exists(save_path):
            self.logger.info(f"Creating directory {save_path}")
            os.makedirs(save_path,exist_ok=True)
        if project_prefix is not None:
            project_names = self.label_studio.get_projects_by_prefix(project_prefix)
        successful_projects = []
        if project_names is not None:
            for project_name in project_names:
                _ = self.label_studio.export_annotations(project_name=project_name,export_location=save_path, export_type="JSON")
                successful_projects.append(project_name)
        for project in range(len(successful_projects)):
            if project_names[project] not in successful_projects:
                self.logger.warning(f"Project {project_names[project]} not found")
        return successful_projects

    def generate_id_config(self, **kwargs):
        successful_projects = self.export_projects(**kwargs)
        
            

                
                
        
