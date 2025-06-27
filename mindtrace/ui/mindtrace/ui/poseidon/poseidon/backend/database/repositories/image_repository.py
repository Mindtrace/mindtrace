from poseidon.backend.database.models.image import Image
from poseidon.backend.core.config import settings
from mindtrace.database.backends.mongo_odm_backend import MongoMindtraceODMBackend
from typing import List, Dict, Optional

backend = MongoMindtraceODMBackend(Image, db_uri=settings.MONGO_URI, db_name=settings.DB_NAME)

class ImageRepository:
    @staticmethod
    async def get_images_paginated(page: int = 1, page_size: int = 24, filters: Optional[Dict] = None) -> Dict:
        """Get paginated images with optional filters"""
        await backend.initialize()
        
        query = filters or {}
        skip = (page - 1) * page_size
        
        images = await backend.find(query, skip=skip, limit=page_size, sort=[("created_at", -1)])
        total_count = await backend.count(query)
        
        return {
            "images": images,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    
    @staticmethod
    async def get_by_id(image_id: str) -> Optional[Image]:
        """Get image by ID"""
        await backend.initialize()
        return await backend.get_by_id(image_id)
    
    @staticmethod
    async def create_image(image_data: dict) -> Image:
        """Create new image record"""
        await backend.initialize()
        image = Image(**image_data)
        return await backend.insert(image)
    
    @staticmethod
    async def update_image(image_id: str, update_data: dict) -> Optional[Image]:
        """Update image record"""
        await backend.initialize()
        return await backend.update(image_id, update_data)
    
    @staticmethod
    async def delete_image(image_id: str) -> bool:
        """Delete image record"""
        await backend.initialize()
        return await backend.delete(image_id)
    
    @staticmethod
    async def search_images(query: str, page: int = 1, page_size: int = 24) -> Dict:
        """Search images by filename or tags"""
        await backend.initialize()
        
        search_filter = {
            "$or": [
                {"filename": {"$regex": query, "$options": "i"}},
                {"tags": {"$in": [query]}},
                {"metadata.description": {"$regex": query, "$options": "i"}}
            ]
        }
        
        return await ImageRepository.get_images_paginated(page, page_size, search_filter) 