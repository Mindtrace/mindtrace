from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Type
import sys

from poseidon.backend.database.models.user import User
from poseidon.backend.database.models.organization import Organization
from poseidon.backend.database.models.project import Project
from poseidon.backend.database.models.project_assignment import ProjectAssignment
from poseidon.backend.database.models.project_license import ProjectLicense
from poseidon.backend.database.models.image import Image
from poseidon.backend.database.models.camera import Camera
from poseidon.backend.database.models.model import Model
from poseidon.backend.database.models.model_deployment import ModelDeployment
from poseidon.backend.database.models.scan import Scan
from poseidon.backend.database.models.scan_image import ScanImage
from poseidon.backend.database.models.scan_classification import ScanClassification
from poseidon.backend.core.config import settings

# Global client and initialization state
_client = None
_is_initialized = False

def rebuild_all_models():
    """Rebuild all models in the correct order to resolve forward references."""
    try:
        # Get all modules that contain models
        organization_module = sys.modules['poseidon.backend.database.models.organization']
        project_module = sys.modules['poseidon.backend.database.models.project']
        user_module = sys.modules['poseidon.backend.database.models.user']
        project_assignment_module = sys.modules['poseidon.backend.database.models.project_assignment']
        project_license_module = sys.modules['poseidon.backend.database.models.project_license']
        image_module = sys.modules['poseidon.backend.database.models.image']
        camera_module = sys.modules['poseidon.backend.database.models.camera']
        model_module = sys.modules['poseidon.backend.database.models.model']
        model_deployment_module = sys.modules['poseidon.backend.database.models.model_deployment']
        scan_module = sys.modules['poseidon.backend.database.models.scan']
        scan_image_module = sys.modules['poseidon.backend.database.models.scan_image']
        scan_classification_module = sys.modules['poseidon.backend.database.models.scan_classification']
        
        # Add all models to each module's global namespace for cross-references
        models_dict = {
            'Organization': Organization,
            'Project': Project,
            'User': User,
            'ProjectAssignment': ProjectAssignment,
            'ProjectLicense': ProjectLicense,
            'Image': Image,
            'Camera': Camera,
            'Model': Model,
            'ModelDeployment': ModelDeployment,
            'Scan': Scan,
            'ScanImage': ScanImage,
            'ScanClassification': ScanClassification,
        }
        
        for module in [organization_module, project_module, user_module, project_assignment_module, project_license_module, camera_module, model_module, model_deployment_module, scan_module, scan_image_module, scan_classification_module, image_module]:
            for name, model_class in models_dict.items():
                setattr(module, name, model_class)
        
        # Rebuild models in dependency order
        # 1. Organization has no dependencies
        Organization.model_rebuild()
        
        # 2. Project and User have circular dependencies, so rebuild both
        Project.model_rebuild()
        
        User.model_rebuild()
        
        # 3. ProjectAssignment and ProjectLicense depend on User and Project
        ProjectAssignment.model_rebuild()
        
        ProjectLicense.model_rebuild()
        print("✓ ProjectLicense model rebuilt")
        
        # 4. Image depends on Organization, Project, and User
        Image.model_rebuild()
        
        # 4. Camera depends on Organization, Project, and User
        Camera.model_rebuild()
        print("✓ Camera model rebuilt")
        
        Model.model_rebuild()
        
        ModelDeployment.model_rebuild()
        print("✓ ModelDeployment model rebuilt")
        
        # 4. Scan models - rebuild in dependency order
        Scan.model_rebuild()
        print("✓ Scan model rebuilt")
        
        ScanImage.model_rebuild()
        print("✓ ScanImage model rebuilt")
        
        ScanClassification.model_rebuild()
        print("✓ ScanClassification model rebuilt")
        
        print("✓ All models rebuilt successfully")
        
    except Exception as e:
        raise

async def initialize_database():
    """Initialize the database with all models registered to resolve ForwardRef links."""
    global _client, _is_initialized
    
    if _is_initialized:
        return _client
    
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    
    # Register ALL models with Beanie at once to resolve ForwardRef links
    document_models = [
        Organization,  # Put Organization first so it's defined before other models
        Project,       # Put Project before models that reference it
        User,         # Put User before models that reference it
        ProjectAssignment,  # Put ProjectAssignment after User and Project
        ProjectLicense,     # Put ProjectLicense after User, Project, and Organization
        Image,        # Put Image after Organization, Project, and User
        Camera,
        Model,
        ModelDeployment,
        Scan,         # Put Scan before models that reference it
        ScanImage,    # Put ScanImage before ScanClassification
        ScanClassification,
    ]
    
    # Let Beanie handle the model initialization and forward reference resolution
    await init_beanie(
        database=_client[settings.DB_NAME],
        document_models=document_models
    )
    
    # Rebuild all models to ensure forward references are resolved
    rebuild_all_models()
    
    _is_initialized = True
    return _client

def get_database_client():
    """Get the database client (must call initialize_database first)."""
    global _client
    return _client

def is_database_initialized():
    """Check if database has been initialized."""
    global _is_initialized
    return _is_initialized 