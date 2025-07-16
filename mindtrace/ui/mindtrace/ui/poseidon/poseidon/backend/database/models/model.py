from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import List, Optional, Dict, Any
from datetime import datetime

class Model(MindtraceDocument):
    name: str  # Model identifier
    description: str
    version: str
    organization_id: str
    created_by: str
    
    # Model metadata
    type: Optional[str] = ""  # "classification", "detection", "segmentation", etc.
    framework: Optional[str] = ""  # 
    input_format: Optional[str] = ""  # "image", "video", "text", etc.
    output_format: Optional[str] = ""  # "probabilities", "bounding_boxes", etc.
    
    # Model files and paths
    model_path: Optional[str] = ""
    config_path: Optional[str] = ""
    weights_path: Optional[str] = ""
    
    
    # Model validation and deployment
    validation_status: Optional[str] = "pending"  # "pending", "validated", "failed"
    deployment_ready: bool = False
    
    # Model metadata and tags
    metadata: Dict[str, Any] = {}
    tags: List[str] = []
    
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    
    def __init__(self, **data):
        if 'created_at' not in data or not data['created_at']:
            data['created_at'] = datetime.now().isoformat()
        if 'updated_at' not in data or not data['updated_at']:
            data['updated_at'] = datetime.now().isoformat()
        super().__init__(**data)
    
    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now().isoformat()
    
    def update_validation_status(self, status: str):
        """Update model validation status"""
        valid_statuses = ["pending", "validated", "failed"]
        if status in valid_statuses:
            self.validation_status = status
            self.deployment_ready = (status == "validated")
            self.update_timestamp()
    
    def update_metrics(self, accuracy: float = None, precision: float = None, 
                      recall: float = None, f1_score: float = None):
        """Update model performance metrics"""
        if accuracy is not None:
            self.accuracy = accuracy
        if precision is not None:
            self.precision = precision
        if recall is not None:
            self.recall = recall
        if f1_score is not None:
            self.f1_score = f1_score
        self.update_timestamp()
    
    def add_tag(self, tag: str):
        """Add a tag to the model"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.update_timestamp()
    
    def remove_tag(self, tag: str):
        """Remove a tag from the model"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.update_timestamp()
    
    def update_metadata(self, metadata: Dict[str, Any]):
        """Update model metadata"""
        self.metadata.update(metadata)
        self.update_timestamp()
    
    def is_deployment_ready(self) -> bool:
        """Check if model is ready for deployment"""
        return self.deployment_ready and self.validation_status == "validated"
    
    def get_full_name(self) -> str:
        """Get descriptive name for the model"""
        return f"{self.name} v{self.version}"