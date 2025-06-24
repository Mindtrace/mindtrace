from mindtrace.database.backends.mongo_odm_backend import MindtraceDocument
from typing import List, Optional
from datetime import datetime

class User(MindtraceDocument):
    username: str
    email: str
    password_hash: str
    roles: List[str] = []
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