from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import Dict, Optional, List
from datetime import datetime

class Image(MindtraceDocument):
    filename: str
    gcp_path: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    tags: List[str] = []
    metadata: Dict[str, str] = {}
    uploaded_by: Optional[str] = None
    project: Optional[str] = None
    organization: Optional[str] = None
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