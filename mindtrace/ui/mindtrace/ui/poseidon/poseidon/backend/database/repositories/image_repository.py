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
        image = Image(**image_data)
        return await image.insert()

    @staticmethod
    async def get_by_id(image_id: str) -> Optional[Image]:
        """Get image by ID"""
        await ImageRepository._ensure_init()
        try:
            return await Image.get(image_id)
        except:
            return None

    @staticmethod
    async def get_by_filename(filename: str) -> Optional[Image]:
        """Get image by filename"""
        await ImageRepository._ensure_init()
        return await Image.find_one(Image.filename == filename)

    @staticmethod
    async def get_by_project(project_id: str) -> List[Image]:
        """Get all images for a project"""
        await ImageRepository._ensure_init()
        return await Image.find(Image.project == project_id).to_list()

    @staticmethod
    async def get_by_organization(organization_id: str) -> List[Image]:
        """Get all images for an organization"""
        await ImageRepository._ensure_init()
        return await Image.find(Image.organization == organization_id).to_list()

    @staticmethod
    async def get_all() -> List[Image]:
        """Get all images"""
        await ImageRepository._ensure_init()
        return await Image.find_all().to_list()

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
    async def search_images(query: str, page: int = 1, page_size: int = 24) -> Dict:
        """Search images by filename or tags"""
        await ImageRepository._ensure_init()
        
        search_filter = {
            "$or": [
                {"filename": {"$regex": query, "$options": "i"}},
                {"tags": {"$in": [query]}},
                {"metadata.description": {"$regex": query, "$options": "i"}}
            ]
        }
        
        return await ImageRepository.get_images_paginated(page, page_size, search_filter)
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