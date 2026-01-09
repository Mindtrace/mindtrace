from typing import Dict, Any, List, Callable, Union
from mindtrace.datalake import Datalake
from mindtrace.models import BaseModel
from mindtrace.core import Worker
from mindtrace.registry import Registry
from mindtrace.models import ClassificationModel, DetectionModel, SegmentationModel


class AnnotatorWorker(Worker):
    """
    Static worker that runs inference using models from Registry.
    Loads datasets from datalake for each job execution.
    
    Job inputs:
    - model: str | ModelBase
    - registry_path: str (optional, for loading models by name)
    - dataset: str (dataset name in datalake)
    - version: str (default "lastest")
    - output_callback: Callable (optional)
    - output_key: str (optional)
    """
    
    def __init__(self, model: Union[str, BaseModel], registry_path: str = None):
        """Initialize Annotator with model from registry or direct model instance."""
        self.registry = Registry(path=registry_path) if registry_path else None
        self.datalake = Datalake()
        
        if isinstance(model, str):
            if not self.registry:
                raise ValueError("Registry path required when loading model by name")
            self.model = self.registry.load(model)
        elif isinstance(model, (ClassificationModel, DetectionModel, SegmentationModel)):
            self.model = model
        else:
            raise NotImplementedError("Model type not supported")
        
        if isinstance(self.model, ClassificationModel):
            self.inference = self.model.classify
        elif isinstance(self.model, DetectionModel):
            self.inference = self.model.detect
        elif isinstance(self.model, SegmentationModel):
            self.inference = self.model.segment
    
    def run(self, job) -> Dict[str, Any]:
        """Execute annotation job on dataset loaded from datalake."""
        dataset_name = job.get('dataset_name_in_datalake')
        version = job.get('version', 'latest')
        self.dataset = self.datalake.load(dataset_name, version=version)
        return
    
    def predict_dataset(self, output_callback: Callable = None, *args, **kwargs) -> List[Dict[str, Any]]:
       pass