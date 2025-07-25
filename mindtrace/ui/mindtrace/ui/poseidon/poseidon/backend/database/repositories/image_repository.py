from poseidon.backend.database.models.image import Image
from poseidon.backend.database.init import initialize_database
from typing import Optional, List, Dict

class ImageRepository:

    @staticmethod
    async def _ensure_init():
        """Ensure database is initialized before operations"""
        await initialize_database()

    @staticmethod
    async def get_images_paginated(page: int = 1, page_size: int = 24, filters: Optional[Dict] = None) -> Dict:
        """Get paginated images with optional filters"""
        await ImageRepository._ensure_init()

        query = filters or {}
        skip = (page - 1) * page_size
        
        # Use correct Beanie query syntax
        if query:
            images = await Image.find(query).skip(skip).limit(page_size).sort([("created_at", -1)]).to_list()
            total_count = await Image.find(query).count()
        else:
            images = await Image.find_all().skip(skip).limit(page_size).sort([("created_at", -1)]).to_list()
            total_count = await Image.find_all().count()
        
        return {
            "images": images,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    
    @staticmethod
    async def create(image_data: dict) -> Image:
        """Create a new image"""
        await ImageRepository._ensure_init()
        
        # Convert uploaded_by_id to Link[User] if provided
        if "uploaded_by_id" in image_data:
            from poseidon.backend.database.models.user import User
            user_id = image_data.pop("uploaded_by_id")
            user = await User.get(user_id)
            image_data["uploaded_by"] = user
        
        # Convert project_id to Link[Project] if provided
        if "project_id" in image_data:
            from poseidon.backend.database.models.project import Project
            project_id = image_data.pop("project_id")
            project = await Project.get(project_id)
            image_data["project"] = project
        
        # Convert organization_id to Link[Organization] if provided
        if "organization_id" in image_data:
            from poseidon.backend.database.models.organization import Organization
            org_id = image_data.pop("organization_id")
            organization = await Organization.get(org_id)
            image_data["organization"] = organization
        
        image = Image(**image_data)
        return await image.insert()

    @staticmethod
    async def get_by_id(image_id: str) -> Optional[Image]:
        """Get image by ID"""
        await ImageRepository._ensure_init()
        try:
            image = await Image.get(image_id)
            if image:
                await image.fetch_all_links()
            return image
        except:
            return None

    @staticmethod
    async def get_by_filename(filename: str) -> Optional[Image]:
        """Get image by filename"""
        await ImageRepository._ensure_init()
        image = await Image.find_one(Image.filename == filename)
        if image:
            await image.fetch_all_links()
        return image

    @staticmethod
    async def get_by_project(project_id: str) -> List[Image]:
        """Get all images for a project"""
        await ImageRepository._ensure_init()
        try:
            from poseidon.backend.database.models.project import Project
            project = await Project.get(project_id)
            if not project:
                return []
            images = await Image.find(Image.project.id == project.id).to_list()
            for image in images:
                await image.fetch_all_links()
            return images
        except:
            return []

    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Image]:
        """Get all images for an organization"""
        await ImageRepository._ensure_init()
        try:
            from poseidon.backend.database.models.organization import Organization
            organization = await Organization.get(organization_id)
            if not organization:
                return []
            images = await Image.find(Image.organization.id == organization.id).to_list()
            for image in images:
                await image.fetch_all_links()
            return images
        except:
            return []

    @staticmethod
    async def get_all() -> List[Image]:
        """Get all images"""
        await ImageRepository._ensure_init()
        images = await Image.find_all().to_list()
        for image in images:
            await image.fetch_all_links()
        return images

    @staticmethod
    async def update(image_id: str, update_data: dict) -> Optional[Image]:
        """Update image"""
        await ImageRepository._ensure_init()
        try:
            image = await Image.get(image_id)
            if image:
                for key, value in update_data.items():
                    if hasattr(image, key):
                        setattr(image, key, value)
                image.update_timestamp()
                await image.save()
                return image
        except:
            pass
        return None

    @staticmethod
    async def delete(image_id: str) -> bool:
        """Delete image"""
        await ImageRepository._ensure_init()
        try:
            image = await Image.get(image_id)
            if image:
                await image.delete()
                return True
        except:
            pass
        return False

    @staticmethod
    async def search_images(search_query: str, page: int = 1, page_size: int = 24) -> Dict:
        """Search images by query with pagination"""
        await ImageRepository._ensure_init()
        
        skip = (page - 1) * page_size
        
        # Create search filter for filename, tags, or metadata
        search_filter = {
            "$or": [
                {"filename": {"$regex": search_query, "$options": "i"}},
                {"tags": {"$in": [{"$regex": search_query, "$options": "i"}]}},
                {"metadata": {"$regex": search_query, "$options": "i"}}
            ]
        }
        
        images = await Image.find(search_filter).skip(skip).limit(page_size).sort([("created_at", -1)]).to_list()
        total_count = await Image.find(search_filter).count()
        
        # Fetch all links for each image
        for image in images:
            await image.fetch_all_links()
        
        return {
            "images": images,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    @staticmethod
    async def search_by_tags(tags: List[str]) -> List[Image]:
        """Search images by tags"""
        await ImageRepository._ensure_init()
        return await Image.find({"tags": {"$in": tags}}).to_list()

    @staticmethod
    async def get_by_uploaded_by(user_id: str) -> List[Image]:
        """Get images uploaded by a specific user"""
        await ImageRepository._ensure_init()
        return await Image.find(Image.uploaded_by == user_id).to_list() 