#!/usr/bin/env python3
"""
Line Insights Database Seeding Script

This script creates sample data for testing the Line Insights dashboard.
It populates the database with realistic production line monitoring data.

Run with: python seed_line_insights_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import List

# Add the project directory to Python path
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from poseidon.backend.database.init import initialize_database
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.backend.database.repositories.camera_repository import CameraRepository
from poseidon.backend.database.repositories.scan_repository import ScanRepository
from poseidon.backend.database.repositories.scan_classification_repository import ScanClassificationRepository
from poseidon.backend.database.repositories.scan_image_repository import ScanImageRepository
from poseidon.backend.database.models.enums import (
    SubscriptionPlan, ProjectStatus, CameraStatus, ScanStatus, ScanImageStatus
)


class LineInsightsSeeder:
    def __init__(self):
        self.organizations = []
        self.projects = []
        self.cameras = []
        self.defect_types = [
            "Surface Scratch", "Color Mismatch", "Dimension Error", 
            "Missing Component", "Surface Dent", "Alignment Issue",
            "Material Defect", "Finish Quality", "Assembly Error", "Packaging Issue"
        ]
    
    async def seed_all(self):
        """Seed all data for Line Insights dashboard testing."""
        print("🌱 Starting Line Insights data seeding...")
        
        await initialize_database()
        
        # Create organizations (plants)
        await self.create_organizations()
        
        # Create projects (production lines)
        await self.create_projects()
        
        # Create cameras for each project
        await self.create_cameras()
        
        # Create scan data (parts processing)
        await self.create_scan_data()
        
        print("✅ Line Insights data seeding completed!")
        print("\n📊 Dashboard Data Summary:")
        print(f"   • {len(self.organizations)} Organizations (Plants)")
        print(f"   • {len(self.projects)} Projects (Production Lines)")
        print(f"   • {len(self.cameras)} Cameras")
        print(f"   • ~{len(self.projects) * 300} Scans (last 30 days)")
        print(f"   • ~{len(self.projects) * 150} Classifications")
        
        print("\n🚀 You can now view realistic data in the Line Insights dashboard!")
        print("   Visit: /line-insights")
    
    async def create_organizations(self):
        """Create sample organizations (manufacturing plants)."""
        print("📍 Creating organizations (plants)...")
        
        org_configs = [
            {
                "name": "MindTrace Demo Plant",
                "description": "Main demonstration manufacturing facility",
                "subscription_plan": SubscriptionPlan.ENTERPRISE,
                "max_users": 100,
                "max_projects": 50,
            },
            {
                "name": "North Factory",
                "description": "Northern production facility",
                "subscription_plan": SubscriptionPlan.PREMIUM,
                "max_users": 50,
                "max_projects": 20,
            }
        ]
        
        for config in org_configs:
            org = await OrganizationRepository.create_organization(config)
            self.organizations.append(org)
            print(f"   ✓ Created organization: {org.name}")
    
    async def create_projects(self):
        """Create sample projects (production lines)."""
        print("🏭 Creating projects (production lines)...")
        
        line_configs = [
            # Demo Plant Lines
            {"name": "Assembly Line A", "description": "Primary assembly line for Product A"},
            {"name": "Assembly Line B", "description": "Secondary assembly line for Product B"}, 
            {"name": "Quality Control Line", "description": "Final quality inspection line"},
            {"name": "Packaging Line", "description": "Product packaging and labeling"},
            
            # North Factory Lines  
            {"name": "Production Line 1", "description": "Main production line"},
            {"name": "Testing Line", "description": "Product testing and validation"},
        ]
        
        lines_per_org = len(line_configs) // len(self.organizations)
        
        for i, org in enumerate(self.organizations):
            start_idx = i * lines_per_org
            end_idx = start_idx + lines_per_org
            org_lines = line_configs[start_idx:end_idx]
            
            for line_config in org_lines:
                project_data = {
                    **line_config,
                    "organization_id": str(org.id),
                    "status": ProjectStatus.ACTIVE,
                    "project_type": "INSPECTION",
                    "tags": ["production", "quality-control"],
                }
                
                project = await ProjectRepository.create_project(project_data)
                self.projects.append(project)
                print(f"   ✓ Created project: {project.name} (Org: {org.name})")
    
    async def create_cameras(self):
        """Create cameras for each production line."""
        print("📹 Creating cameras...")
        
        camera_positions = [
            "Station 1 - Intake", "Station 2 - Assembly", 
            "Station 3 - Quality Check", "Station 4 - Output"
        ]
        
        for project in self.projects:
            for i, position in enumerate(camera_positions):
                camera_data = {
                    "name": f"{position}",
                    "backend": "opencv",
                    "device_name": f"cam_{project.name.lower().replace(' ', '_')}_{i+1}",
                    "status": CameraStatus.ACTIVE,
                    "configuration": {
                        "resolution": "1920x1080",
                        "fps": 30,
                        "position": position,
                    },
                    "organization_id": str(project.organization.id),
                    "project_id": str(project.id),
                    "location": position,
                    "model_info": f"Industrial Camera {i+1}",
                }
                
                camera = await CameraRepository.create_or_update(camera_data)
                self.cameras.append(camera)
        
        print(f"   ✓ Created {len(self.cameras)} cameras across all projects")
    
    async def create_scan_data(self):
        """Create realistic scan data for the last 30 days."""
        print("🔍 Creating scan data (this may take a moment)...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        current_date = start_date
        
        total_scans = 0
        total_classifications = 0
        
        while current_date <= end_date:
            # Skip weekends for more realistic factory data
            if current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                current_date += timedelta(days=1)
                continue
            
            for project in self.projects:
                # Generate 8-15 scans per project per day
                daily_scans = random.randint(8, 15)
                
                for _ in range(daily_scans):
                    scan_time = current_date.replace(
                        hour=random.randint(8, 17),  # Work hours
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59)
                    )
                    
                    # Create scan
                    scan_data = {
                        "organization": project.organization,
                        "project": project,
                        "model_deployment": None,  # Optional field
                        "serial_number": f"SCAN_{int(scan_time.timestamp())}_{random.randint(1000, 9999)}",
                        "status": random.choices(
                            [ScanStatus.COMPLETED, ScanStatus.FAILED],
                            weights=[0.92, 0.08]  # 92% success rate
                        )[0],
                        "cls_result": random.choices(
                            ["pass", "defective"], 
                            weights=[0.85, 0.15]  # 15% defect rate
                        )[0],
                        "cls_confidence": random.uniform(0.7, 0.99),
                        "cls_pred_time": random.uniform(0.1, 0.8),
                    }
                    
                    scan = await ScanRepository.create(scan_data)
                    total_scans += 1
                    
                    # For defective scans, create classifications
                    if scan.cls_result == "defective":
                        # Each defective scan has 1-3 defect classifications
                        num_defects = random.randint(1, 3)
                        
                        for _ in range(num_defects):
                            defect_type = random.choice(self.defect_types)
                            
                            # Create scan image first
                            image_data = {
                                "organization": project.organization,
                                "project": project,
                                "camera": random.choice([c for c in self.cameras if str(c.project.id) == str(project.id)]),
                                "scan": scan,
                                "status": ScanImageStatus.PROCESSED,
                                "file_name": f"scan_{scan.serial_number}_{random.randint(1, 4)}.jpg",
                                "path": f"scans/{scan.serial_number}/",
                                "bucket_name": "mindtrace-scans",
                            }
                            
                            scan_image = await ScanImageRepository.create(image_data)
                            
                            # Create classification
                            classification_data = {
                                "image": scan_image,
                                "scan": scan,
                                "name": defect_type,
                                "cls_confidence": random.uniform(0.6, 0.95),
                                "cls_pred_time": random.uniform(0.05, 0.3),
                                # Bounding box for defect location
                                "det_cls": defect_type,
                                "det_x": random.randint(50, 800),
                                "det_y": random.randint(50, 600),
                                "det_w": random.randint(30, 150),
                                "det_h": random.randint(30, 150),
                            }
                            
                            await ScanClassificationRepository.create(classification_data)
                            total_classifications += 1
            
            current_date += timedelta(days=1)
            
            # Progress indicator
            if current_date.day % 5 == 0:
                days_processed = (current_date - start_date).days
                print(f"   📅 Processed {days_processed} days of data...")
        
        print(f"   ✓ Created {total_scans} scans with {total_classifications} defect classifications")
    
    async def cleanup_existing_data(self):
        """Clean up existing test data (optional)."""
        print("🧹 Cleaning up existing test data...")
        # Implementation depends on your repository delete methods
        # This is optional - you may want to keep existing data
        pass


async def main():
    """Main seeding function."""
    seeder = LineInsightsSeeder()
    
    try:
        await seeder.seed_all()
    except Exception as e:
        print(f"❌ Error during seeding: {e}")
        print("Make sure your database is running and accessible.")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🌱 MindTrace Line Insights Database Seeder")
    print("=" * 50)
    asyncio.run(main())