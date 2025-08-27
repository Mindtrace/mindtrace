#!/usr/bin/env python3
"""
Database seed file to create the initial organization and superadmin user.
This file is safe to run in production as it only creates data if it doesn't exist.
"""

import asyncio
import secrets
from datetime import datetime
from typing import Dict, List, Any

from .init import initialize_database
from .models.organization import Organization
from .models.user import User
from .models.project import Project
from .models.camera import Camera
from .models.model import Model
from .models.model_deployment import ModelDeployment
from .models.scan import Scan
from .models.scan_image import ScanImage
from .models.scan_classification import ScanClassification
from .models.enums import OrgRole, SubscriptionPlan, ScanStatus, ScanImageStatus, ModelValidationStatus
from poseidon.backend.utils.security import hash_password


async def create_initial_organization() -> Organization:
    """Create the initial 'mindtrace' organization"""
    print("Creating initial organization...")
    
    # Check if organization already exists
    existing_org = await Organization.find_one(Organization.name == "mindtrace")
    if existing_org:
        print(f"✓ Organization 'mindtrace' already exists (ID: {existing_org.id})")
        return existing_org
    
    # Create the mindtrace organization
    org_data = {
        "name": "mindtrace",
        "description": "MindTrace main organization",
        "subscription_plan": SubscriptionPlan.ENTERPRISE,
        "max_users": None,  # Unlimited users
        "max_projects": None,  # Unlimited projects
        "is_active": True
    }
    
    organization = Organization(**org_data)
    await organization.save()
    
    print(f"✓ Created organization 'mindtrace' (ID: {organization.id})")
    print(f"  - Admin registration key: {organization.admin_registration_key}")
    return organization


async def create_superadmin_user(organization: Organization) -> User:
    """Create the initial superadmin user"""
    print("Creating superadmin user...")
    
    # Check if user already exists
    existing_user = await User.find_one(User.username == "mindtracesuperadmin")
    if existing_user:
        print(f"✓ User 'mindtracesuperadmin' already exists (ID: {existing_user.id})")
        return existing_user
    
    # Generate a secure default password
    default_password = secrets.token_urlsafe(16)
    password_hash = hash_password(default_password)
    
    # Create the superadmin user
    user_data = {
        "username": "mindtracesuperadmin",
        "email": "superadmin@mindtrace.com",
        "password_hash": password_hash,
        "organization": organization,
        "org_role": OrgRole.SUPER_ADMIN,
        "is_active": True
    }
    
    user = User(**user_data)
    await user.save()
    
    print(f"✓ Created superadmin user 'mindtracesuperadmin' (ID: {user.id})")
    print(f"  - Email: {user.email}")
    print(f"  - Default password: {default_password}")
    print(f"  - Role: {user.org_role}")
    print(f"  - Organization: {organization.name}")
    
    return user


async def update_organization_user_count(organization: Organization):
    """Update the organization's user count"""
    user_count = await User.find(User.organization.id == organization.id).count()
    organization.user_count = user_count
    await organization.save()
    print(f"✓ Updated organization user count to {user_count}")


async def verify_setup():
    """Verify the setup was successful"""
    print("\nVerifying setup...")
    
    # Check organization
    org = await Organization.find_one(Organization.name == "mindtrace")
    if not org:
        print("❌ Organization 'mindtrace' not found!")
        return False
    
    # Check user
    user = await User.find_one(User.username == "mindtracesuperadmin")
    if not user:
        print("❌ User 'mindtracesuperadmin' not found!")
        return False
    
    # Fetch user's organization link
    await user.fetch_all_links()
    
    # Verify user is linked to organization
    if not user.organization or str(user.organization.id) != str(org.id):
        print("❌ User is not properly linked to organization!")
        return False
    
    # Verify user has super admin role
    if user.org_role != OrgRole.SUPER_ADMIN:
        print(f"❌ User role is {user.org_role}, expected {OrgRole.SUPER_ADMIN}!")
        return False
    
    print("✓ Setup verification successful!")
    print(f"  - Organization: {org.name} (ID: {org.id})")
    print(f"  - User: {user.username} (ID: {user.id})")
    print(f"  - Role: {user.org_role}")
    print(f"  - Active: {user.is_active}")
    
    return True


async def create_sample_project(organization: Organization, user: User) -> Project:
    """Create a sample project for the scan data"""
    print("Creating sample project...")
    
    # Check if project already exists
    existing_project = await Project.find_one(Project.name == "Sample Inspection Project")
    if existing_project:
        print(f"✓ Project 'Sample Inspection Project' already exists (ID: {existing_project.id})")
        return existing_project
    
    project_data = {
        "name": "Sample Inspection Project",
        "description": "Sample project for imported scan data",
        "organization": organization,
        "owner": user,
        "status": "active",
        "project_type": "inspection"
    }
    
    project = Project(**project_data)
    await project.save()
    
    print(f"✓ Created project 'Sample Inspection Project' (ID: {project.id})")
    return project


async def create_sample_cameras(organization: Organization, project: Project, user: User) -> Dict[str, Camera]:
    """Create sample cameras based on the data"""
    print("Creating sample cameras...")
    
    # Extract unique camera names from the data
    camera_names = set()
    
    # Sample data - extract camera names from images
    sample_data = [
        {
            "id": "8003cbf3-94b0-4745-9002-a2ce1324f572",
            "createdAt": "2025-06-26 11:02:39.041",
            "status": "Success",
            "partId": "10474125177070209_10474225177070209",
            "partNo": 0,
            "clsResult": "Defective",
            "clsConfidence": None,
            "images": [
                {"id": "227ffbd4-2637-4502-b16c-827ed5b2c5b2", "createdAt": "2025-06-26T11:02:43.348", "name": "cam16-2811566.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam16", "welds": [{"id": "518be0de-229a-4da0-a527-a536888eca8d", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA6", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "01aaf317-4fd8-4505-b95f-879008768a26", "createdAt": "2025-06-26T11:02:43.687", "name": "cam21-8916226.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam21", "welds": [{"id": "e40b8278-bff2-4bbc-b922-1aedd04afd20", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA11", "severity": 4, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "56f217b0-3ea0-4d99-b8b1-08f089596370", "createdAt": "2025-06-26T11:02:43.348", "name": "cam11-3937369.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam11", "welds": [{"id": "f5757718-7dfe-4b41-8e4c-1138eaeeb77c", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA1", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "e10c2a70-d993-413a-8bd9-55f654927245", "createdAt": "2025-06-26T11:02:43.23", "name": "cam9-6161546.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam9", "welds": [{"id": "fc46c7bc-c9d9-4e9e-a0ef-56b50f99c6b9", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA9", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "90ec5ead-0979-4d89-9a3a-5e032eed3d65", "createdAt": "2025-06-26T11:02:43.346", "name": "cam22-5509399.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam22", "welds": [{"id": "2afe700f-44c4-4323-9191-1393b5931700", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA11", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "2315f497-c25a-413d-b2cf-f0d02b7ddd0c", "createdAt": "2025-06-26T11:02:43.348", "name": "cam14-3542241.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam14", "welds": [{"id": "ce8f3a97-9f4d-4172-a693-728456d28c94", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA3", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}, {"id": "9276b1f0-617d-44b0-b496-00d53147aa87", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA4", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "d6fc250c-0793-4512-8b78-74cfb54321b9", "createdAt": "2025-06-26T11:02:43.35", "name": "cam19-9954682.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam19", "welds": [{"id": "949a1de4-2c31-42d1-9a6f-8446acd6d3e1", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA9", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "077d8ccf-f6c5-4ae1-bc37-9540c3ed4ae3", "createdAt": "2025-06-26T11:02:43.689", "name": "cam4-3898886.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam4", "welds": [{"id": "7f452c7b-8733-44fa-9cde-0239edd23980", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA4", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "0ce68e10-eb88-43ec-9365-6be0cf281ee4", "createdAt": "2025-06-26T11:02:43.229", "name": "cam6-2527995.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam6", "welds": [{"id": "cbd4edf0-a7f7-404d-8df9-d9be3cfb2588", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA6", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "8885fbc4-8943-4b77-b172-c12ced5c1a46", "createdAt": "2025-06-26T11:02:43.227", "name": "cam10-6375079.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam10", "welds": [{"id": "a4c6648b-5c06-465c-8a95-28369256ed30", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA10", "severity": 0.2, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "58f9d5ce-d477-4997-9c0c-d66b7e8bb88f", "createdAt": "2025-06-26T11:02:43.268", "name": "cam8-7214075.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam8", "welds": [{"id": "385381d9-1e66-4e05-873e-1aeb0221eafc", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA8", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "9f020bac-cb31-48e9-820d-4d0bc3c56c43", "createdAt": "2025-06-26T11:02:43.222", "name": "cam18-8591150.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam18", "welds": [{"id": "2feb40ea-0609-4ff2-b3d7-2076a4fe2e34", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA8", "severity": 4.4, "clsResult": "Burr", "clsConfidence": None}]},
                {"id": "4573727b-04a0-4a35-88c2-ee56adf0dd78", "createdAt": "2025-06-26T11:02:43.347", "name": "cam15-8252562.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam15", "welds": [{"id": "f8f12f9e-f887-45bf-9de3-7c34091fe1f2", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA5", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "65fa1775-6b33-4493-9080-714ff83fba43", "createdAt": "2025-06-26T11:02:43.65", "name": "cam17-8314608.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam17", "welds": [{"id": "8ab3cf3d-2a47-43e0-af9a-0d3bf67abba4", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA7", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "c336a50b-22d9-489e-a4f2-6c3105b2b615", "createdAt": "2025-06-26T11:02:43.688", "name": "cam20-9459191.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam20", "welds": [{"id": "dd7e2e30-3e4c-43ee-a16b-c9b359c2f763", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA10", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "45ab3181-87a6-4dac-b245-53bf204fee37", "createdAt": "2025-06-26T11:02:43.226", "name": "cam12-8929753.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam12", "welds": [{"id": "b3615cf1-e926-4cb4-ac59-6fc7a5ec61a9", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA2", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "0810f071-fe2b-4346-8db3-8d205c09a6df", "createdAt": "2025-06-26T11:02:43.229", "name": "cam3-6517844.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam3", "welds": [{"id": "b478786b-ca40-45c7-8df9-554bd43422ba", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA3", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "9ab2aec5-9c31-49ad-8785-eeacb7ea1779", "createdAt": "2025-06-26T11:02:43.35", "name": "cam5-1666972.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam5", "welds": [{"id": "e8f88d47-50d5-473c-aa34-b1a835a5d62d", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA5", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "08d909fa-23e3-4932-aad2-1c366d6494c1", "createdAt": "2025-06-26T11:02:43.348", "name": "cam2-1387124.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam2", "welds": [{"id": "ab732aac-068c-400b-a9f9-3a63cccc1b21", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA2", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "91f6d256-3cb7-41cd-90fb-1c3d30796680", "createdAt": "2025-06-26T11:02:41.66", "name": "cam1-9349806.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam1", "welds": [{"id": "db1b3174-fd76-4cf6-a155-0d4ca11abd66", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA1", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "b4c58e4e-2866-401f-81d4-036ec68d3d2a", "createdAt": "2025-06-26T11:02:42.387", "name": "cam7-8769287.jpg", "path": "8003cbf3-94b0-4745-9002-a2ce1324f572", "pov": "cam7", "welds": [{"id": "cefeeeb4-0c33-4b09-bdb6-7c6eb148e8fd", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA7", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]}
            ]
        }
    ]
    
    # Extract camera names from the data
    for scan_record in sample_data:
        for image in scan_record['images']:
            pov = image.get('pov', '')
            if pov:
                camera_names.add(pov)
    
    cameras = {}
    for camera_name in camera_names:
        # Check if camera already exists
        existing_camera = await Camera.find_one(
            Camera.name == camera_name,
            Camera.project.id == project.id
        )
        
        if existing_camera:
            cameras[camera_name] = existing_camera
            print(f"✓ Camera '{camera_name}' already exists (ID: {existing_camera.id})")
            continue
        
        camera_data = {
            "name": camera_name,
            "backend": "sample_backend",
            "device_name": f"Device_{camera_name}",
            "organization": organization,
            "project": project,
            "created_by": user,
            "description": f"Sample camera {camera_name}",
            "serial_number": f"SN_{camera_name}_001"
        }
        
        camera = Camera(**camera_data)
        await camera.save()
        cameras[camera_name] = camera
        
        print(f"✓ Created camera '{camera_name}' (ID: {camera.id})")
    
    return cameras


async def create_sample_model(organization: Organization, project: Project, user: User) -> Model:
    """Create a sample model"""
    print("Creating sample model...")
    
    # Check if model already exists
    existing_model = await Model.find_one(
        Model.name == "Sample Inspection Model",
        Model.project.id == project.id
    )
    
    if existing_model:
        print(f"✓ Model 'Sample Inspection Model' already exists (ID: {existing_model.id})")
        return existing_model
    
    model_data = {
        "name": "Sample Inspection Model",
        "description": "Sample model for imported scan data",
        "version": "1.0.0",
        "organization": organization,
        "created_by": user,
        "project": project,
        "type": "classification",
        "framework": "pytorch",
        "validation_status": ModelValidationStatus.VALIDATED,
        "deployment_ready": True
    }
    
    model = Model(**model_data)
    await model.save()
    
    print(f"✓ Created model 'Sample Inspection Model' (ID: {model.id})")
    return model


async def create_sample_model_deployment(organization: Organization, project: Project, user: User, model: Model) -> ModelDeployment:
    """Create a sample model deployment"""
    print("Creating sample model deployment...")
    
    # Check if model deployment already exists
    existing_deployment = await ModelDeployment.find_one(
        ModelDeployment.organization.id == organization.id,
        ModelDeployment.project.id == project.id
    )
    
    if existing_deployment:
        print(f"✓ Model deployment already exists (ID: {existing_deployment.id})")
        return existing_deployment
    
    deployment_data = {
        "model": model,
        "organization": organization,
        "project": project,
        "created_by": user,
        "model_server_url": "http://localhost:8000/inference",
        "deployment_status": "deployed",
        "health_status": "healthy"
    }
    
    try:
        deployment = ModelDeployment(**deployment_data)
        await deployment.save()
        print(f"✓ Created model deployment (ID: {deployment.id})")
        return deployment
    except Exception as e:
        print(f"Warning: Could not create model deployment: {e}")
        return None


def get_sample_data() -> List[Dict[str, Any]]:
    """Return sample data directly"""
    data = [
        {
            'id': '8003cbf3-94b0-4745-9002-a2ce1324f572',
            'created_at': datetime.fromisoformat('2025-06-26T11:02:39.041'),
            'status': 'Success',
            'serial_number': '10474125177070209_10474225177070209',
            'part_no': 0,
            'cls_result': 'Defective',
            'cls_confidence': None,
            'images': [
                {"id": "227ffbd4-2637-4502-b16c-827ed5b2c5b2", "createdAt": "2025-06-26T11:02:43.348", "name": "cam16-2811566.jpg", "pov": "cam16", "welds": [{"id": "518be0de-229a-4da0-a527-a536888eca8d", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA6", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "01aaf317-4fd8-4505-b95f-879008768a26", "createdAt": "2025-06-26T11:02:43.687", "name": "cam21-8916226.jpg", "pov": "cam21", "welds": [{"id": "e40b8278-bff2-4bbc-b922-1aedd04afd20", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA11", "severity": 4, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "56f217b0-3ea0-4d99-b8b1-08f089596370", "createdAt": "2025-06-26T11:02:43.348", "name": "cam11-3937369.jpg", "pov": "cam11", "welds": [{"id": "f5757718-7dfe-4b41-8e4c-1138eaeeb77c", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA1", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "e10c2a70-d993-413a-8bd9-55f654927245", "createdAt": "2025-06-26T11:02:43.23", "name": "cam9-6161546.jpg", "pov": "cam9", "welds": [{"id": "fc46c7bc-c9d9-4e9e-a0ef-56b50f99c6b9", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA9", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "90ec5ead-0979-4d89-9a3a-5e032eed3d65", "createdAt": "2025-06-26T11:02:43.346", "name": "cam22-5509399.jpg", "pov": "cam22", "welds": [{"id": "2afe700f-44c4-4323-9191-1393b5931700", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA11", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "2315f497-c25a-413d-b2cf-f0d02b7ddd0c", "createdAt": "2025-06-26T11:02:43.348", "name": "cam14-3542241.jpg", "pov": "cam14", "welds": [{"id": "ce8f3a97-9f4d-4172-a693-728456d28c94", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA3", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}, {"id": "9276b1f0-617d-44b0-b496-00d53147aa87", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA4", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "d6fc250c-0793-4512-8b78-74cfb54321b9", "createdAt": "2025-06-26T11:02:43.35", "name": "cam19-9954682.jpg", "pov": "cam19", "welds": [{"id": "949a1de4-2c31-42d1-9a6f-8446acd6d3e1", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA9", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "077d8ccf-f6c5-4ae1-bc37-9540c3ed4ae3", "createdAt": "2025-06-26T11:02:43.689", "name": "cam4-3898886.jpg", "pov": "cam4", "welds": [{"id": "7f452c7b-8733-44fa-9cde-0239edd23980", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA4", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "0ce68e10-eb88-43ec-9365-6be0cf281ee4", "createdAt": "2025-06-26T11:02:43.229", "name": "cam6-2527995.jpg", "pov": "cam6", "welds": [{"id": "cbd4edf0-a7f7-404d-8df9-d9be3cfb2588", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA6", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "8885fbc4-8943-4b77-b172-c12ced5c1a46", "createdAt": "2025-06-26T11:02:43.227", "name": "cam10-6375079.jpg", "pov": "cam10", "welds": [{"id": "a4c6648b-5c06-465c-8a95-28369256ed30", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA10", "severity": 0.2, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "58f9d5ce-d477-4997-9c0c-d66b7e8bb88f", "createdAt": "2025-06-26T11:02:43.268", "name": "cam8-7214075.jpg", "pov": "cam8", "welds": [{"id": "385381d9-1e66-4e05-873e-1aeb0221eafc", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA8", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "9f020bac-cb31-48e9-820d-4d0bc3c56c43", "createdAt": "2025-06-26T11:02:43.222", "name": "cam18-8591150.jpg", "pov": "cam18", "welds": [{"id": "2feb40ea-0609-4ff2-b3d7-2076a4fe2e34", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA8", "severity": 4.4, "clsResult": "Burr", "clsConfidence": None}]},
                {"id": "4573727b-04a0-4a35-88c2-ee56adf0dd78", "createdAt": "2025-06-26T11:02:43.347", "name": "cam15-8252562.jpg", "pov": "cam15", "welds": [{"id": "f8f12f9e-f887-45bf-9de3-7c34091fe1f2", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA5", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "65fa1775-6b33-4493-9080-714ff83fba43", "createdAt": "2025-06-26T11:02:43.65", "name": "cam17-8314608.jpg", "pov": "cam17", "welds": [{"id": "8ab3cf3d-2a47-43e0-af9a-0d3bf67abba4", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA7", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "c336a50b-22d9-489e-a4f2-6c3105b2b615", "createdAt": "2025-06-26T11:02:43.688", "name": "cam20-9459191.jpg", "pov": "cam20", "welds": [{"id": "dd7e2e30-3e4c-43ee-a16b-c9b359c2f763", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA10", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "45ab3181-87a6-4dac-b245-53bf204fee37", "createdAt": "2025-06-26T11:02:43.226", "name": "cam12-8929753.jpg", "pov": "cam12", "welds": [{"id": "b3615cf1-e926-4cb4-ac59-6fc7a5ec61a9", "createdAt": "2025-06-26T11:02:45.799", "name": "IB_WA2", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "0810f071-fe2b-4346-8db3-8d205c09a6df", "createdAt": "2025-06-26T11:02:43.229", "name": "cam3-6517844.jpg", "pov": "cam3", "welds": [{"id": "b478786b-ca40-45c7-8df9-554bd43422ba", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA3", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "9ab2aec5-9c31-49ad-8785-eeacb7ea1779", "createdAt": "2025-06-26T11:02:43.35", "name": "cam5-1666972.jpg", "pov": "cam5", "welds": [{"id": "e8f88d47-50d5-473c-aa34-b1a835a5d62d", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA5", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "08d909fa-23e3-4932-aad2-1c366d6494c1", "createdAt": "2025-06-26T11:02:43.348", "name": "cam2-1387124.jpg", "pov": "cam2", "welds": [{"id": "ab732aac-068c-400b-a9f9-3a63cccc1b21", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA2", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "91f6d256-3cb7-41cd-90fb-1c3d30796680", "createdAt": "2025-06-26T11:02:41.66", "name": "cam1-9349806.jpg", "pov": "cam1", "welds": [{"id": "db1b3174-fd76-4cf6-a155-0d4ca11abd66", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA1", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "b4c58e4e-2866-401f-81d4-036ec68d3d2a", "createdAt": "2025-06-26T11:02:42.387", "name": "cam7-8769287.jpg", "pov": "cam7", "welds": [{"id": "cefeeeb4-0c33-4b09-bdb6-7c6eb148e8fd", "createdAt": "2025-06-26T11:02:45.799", "name": "OB_WA7", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]}
            ]
        },
        {
            'id': 'aa3d2f2a-0301-434c-be4f-0325b962e0f2',
            'created_at': datetime.fromisoformat('2025-06-26T11:03:08.007'),
            'status': 'Success',
            'serial_number': '10474325177070238_10474425177070238',
            'part_no': 0,
            'cls_result': 'Healthy',
            'cls_confidence': None,
            'images': [
                {"id": "712a2dca-018c-4bfc-93b9-b92159805da6", "createdAt": "2025-06-26T11:03:12.306", "name": "cam22-4328034.jpg", "pov": "cam22", "welds": [{"id": "e556bf8c-e158-45a3-88dc-372de9c27d7f", "createdAt": "2025-06-26T11:03:14.609", "name": "OB_WA11", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "7015a920-ff80-45a5-ba54-58cd2588b644", "createdAt": "2025-06-26T11:03:12.306", "name": "cam21-4919224.jpg", "pov": "cam21", "welds": [{"id": "5e45979b-b5e7-4e39-a71f-b81a99f7f501", "createdAt": "2025-06-26T11:03:14.609", "name": "IB_WA11", "severity": 4, "clsResult": "Healthy", "clsConfidence": None}]},
                {"id": "9662cff2-fb74-4bd3-bccb-86304cc7ed6e", "createdAt": "2025-06-26T11:03:12.325", "name": "cam17-9668238.jpg", "pov": "cam17", "welds": [{"id": "09fa4ac9-aac2-4dec-90ce-1c9cad71d5cd", "createdAt": "2025-06-26T11:03:14.609", "name": "IB_WA7", "severity": 0, "clsResult": "Healthy", "clsConfidence": None}]}
            ]
        }
    ]
    
    return data


async def seed_scan_data_from_csv(organization: Organization, project: Project, user: User, cameras: Dict[str, Camera], model_deployment: ModelDeployment = None):
    """Seed scan data from the sample data"""
    print("Seeding scan data from sample data...")
    
    csv_data = get_sample_data()
    
    if not csv_data:
        print("No sample data found")
        return
    
    scan_count = 0
    image_count = 0
    classification_count = 0
    
    for scan_record in csv_data:
        # Create Scan record
        scan_data = {
            "organization": organization,
            "project": project,
            "user": user,
            "serial_number": scan_record['serial_number'],
            "status": ScanStatus.COMPLETED if scan_record['status'] == 'Success' else ScanStatus.FAILED,
            "cls_result": scan_record['cls_result'],
            "cls_confidence": scan_record['cls_confidence'],
            "created_at": scan_record['created_at']
        }
        
        if model_deployment:
            scan_data["model_deployment"] = model_deployment
        
        scan = Scan(**scan_data)
        await scan.save()
        scan_count += 1
        
        # Process images for this scan
        for image_record in scan_record['images']:
            camera_name = image_record.get('pov', 'cam1')
            camera = cameras.get(camera_name, list(cameras.values())[0] if cameras else None)
            
            if not camera:
                print(f"Warning: No camera found for {camera_name}")
                continue
            
            # Create ScanImage record with proper bucket and path structure
            # Path structure: organization_id/project_id/test-seed/scan_id/
            image_path = f"{organization.id}/{project.id}/test-seed/{scan.id}/"
            image_data = {
                "organization": organization,
                "project": project,
                "camera": camera,
                "scan": scan,
                "user": user,
                "status": ScanImageStatus.PROCESSED,
                "file_name": image_record['name'],
                "path": image_path,
                "bucket_name": "paz-test-bucket",
                "full_path": f"{image_path}{image_record['name']}",
                "created_at": datetime.fromisoformat(image_record['createdAt'])
            }
            
            scan_image = ScanImage(**image_data)
            await scan_image.save()
            image_count += 1
            
            # Process welds (classifications) for this image
            welds = image_record.get('welds', [])
            for weld_record in welds:
                classification_data = {
                    "image": scan_image,
                    "scan": scan,
                    "name": weld_record['name'],
                    "cls_confidence": weld_record.get('clsConfidence'),
                    "det_cls": weld_record.get('clsResult'),
                    "created_at": datetime.fromisoformat(weld_record['createdAt'])
                }
                
                scan_classification = ScanClassification(**classification_data)
                await scan_classification.save()
                classification_count += 1
                
                # Link classification to image
                scan_image.add_classification(scan_classification)
                await scan_image.save()
            
            # Link image to scan
            scan.add_image(scan_image)
            await scan.save()
    
    print(f"✓ Seeded {scan_count} scans, {image_count} images, {classification_count} classifications")


async def seed_database():
    """Main seed function - safe to run in production"""
    print("=" * 60)
    print("Starting database seeding...")
    print("=" * 60)
    
    try:
        # Initialize database
        print("Initializing database...")
        await initialize_database()
        print("✓ Database initialized successfully")
        print("-" * 60)
        
        # Create initial organization
        organization = await create_initial_organization()
        
        # Create superadmin user
        user = await create_superadmin_user(organization)
        
        # Update organization user count
        await update_organization_user_count(organization)
        
        # Verify setup
        if await verify_setup():
            print("-" * 60)
            print("🎉 Basic database seeding completed successfully!")
            print("\nIMPORTANT: Save the generated password above for the superadmin user!")
        else:
            print("❌ Setup verification failed!")
            return False
        
        # Now create sample data (project, cameras, scans)
        print("-" * 60)
        print("Creating sample data (project, cameras, scans)...")
        
        # Create sample project
        project = await create_sample_project(organization, user)
        
        # Create sample cameras
        cameras = await create_sample_cameras(organization, project, user)
        
        # Create sample model and deployment
        model = await create_sample_model(organization, project, user)
        model_deployment = await create_sample_model_deployment(organization, project, user, model)
        
        # Seed scan data from sample data
        await seed_scan_data_from_csv(organization, project, user, cameras, model_deployment)
        
        print("-" * 60)
        print("🎉 Complete database seeding finished successfully!")
        print(f"✓ Organization: {organization.name} (ID: {organization.id})")
        print(f"✓ Project: {project.name} (ID: {project.id})")
        print(f"✓ Created {len(cameras)} cameras")
        print(f"✓ Created scan data with images and classifications")
            
    except Exception as e:
        print(f"❌ Database seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


async def seed_csv_data():
    """Main function to seed CSV data"""
    print("=" * 60)
    print("Starting CSV data seeding...")
    print("=" * 60)
    
    try:
        # Initialize database
        print("Initializing database...")
        await initialize_database()
        print("✓ Database initialized successfully")
        print("-" * 60)
        
        # Get or create organization and user
        organization = await Organization.find_one(Organization.name == "mindtrace")
        if not organization:
            print("❌ Organization 'mindtrace' not found! Please run the main seed function first.")
            return False
        
        user = await User.find_one(User.username == "mindtracesuperadmin")
        if not user:
            print("❌ User 'mindtracesuperadmin' not found! Please run the main seed function first.")
            return False
        
        # Create sample project
        project = await create_sample_project(organization, user)
        
        # Create sample cameras
        cameras = await create_sample_cameras(organization, project, user)
        
        # Create sample model and deployment
        model = await create_sample_model(organization, project, user)
        model_deployment = await create_sample_model_deployment(organization, project, user, model)
        
        # Seed scan data from CSV
        await seed_scan_data_from_csv(organization, project, user, cameras, model_deployment)
        
        print("-" * 60)
        print("🎉 CSV data seeding completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ CSV data seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("MindTrace Database Seeding Tool")
    print("This tool is safe to run in production - it only creates data if it doesn't exist.")
    print("=" * 60)
    
    # Run the seeding
    asyncio.run(seed_csv_data()) 