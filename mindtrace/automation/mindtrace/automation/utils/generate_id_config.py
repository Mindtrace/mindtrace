import os
from typing import List

from mindtrace.core import Mindtrace
from mindtrace.automation.label_studio.label_studio_api import LabelStudio
class GenerateIdConfig(Mindtrace):
    def __init__(self, label_studio: LabelStudio, **kwargs):
        super().__init__(**kwargs)
        self.label_studio = label_studio

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

    #def generate_id_config(self, **kwargs):
     #   successful_projects = self.export_projects(**kwargs)

if __name__ == "__main__":
    label_studio = LabelStudio(
        url="http://34.66.135.145:8080/",
        api_key="5c7de958cb0583e9b89f5795cdd9fc053aa105ba"
    )
    generate_id_config = GenerateIdConfig(label_studio)
    generate_id_config.export_projects(save_path="./t_projects", project_prefix="paslin_cam")
        
            

                
                
        
