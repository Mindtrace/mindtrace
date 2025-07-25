import reflex as rx
from poseidon.backend.database.repositories.image_repository import ImageRepository
from typing import List, Optional
from dataclasses import dataclass
from poseidon.backend.cloud.gcs import presign_url

@dataclass
class ImageDict:
    filename: str = ""
    gcp_path: str = ""
    presigned_url: str = ""
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    tags: List[str] = None
    uploaded_by: Optional[str] = None
    project: Optional[str] = None
    organization: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

class ImageState(rx.State):
    images: List[ImageDict] = []
    current_page: int = 1
    page_size: int = 12
    total_pages: int = 0
    total_count: int = 0
    is_loading: bool = False
    
    selected_image: Optional[ImageDict] = None
    show_modal: bool = False
    
    search_query: str = ""
    
    def _safe_convert_to_image_dict(self, img_data) -> ImageDict:
        """Safely convert database data to ImageDict with proper type handling"""
        try:
            # Handle different data sources (dict vs Document object)
            if hasattr(img_data, 'dict'):
                data = img_data.dict()
            elif hasattr(img_data, '__dict__'):
                data = img_data.__dict__
            else:
                data = img_data
                
            # Safe type conversions with defaults
            return ImageDict(
                filename=str(data.get("filename", "")),
                gcp_path=str(data.get("gcp_path", "")),
                presigned_url=str(data.get("presigned_url", "")),
                file_size=int(data.get("file_size")) if data.get("file_size") is not None else None,
                content_type=str(data.get("content_type")) if data.get("content_type") else None,
                width=int(data.get("width")) if data.get("width") is not None else None,
                height=int(data.get("height")) if data.get("height") is not None else None,
                tags=list(data.get("tags", [])) if data.get("tags") else [],
                uploaded_by=str(data.get("uploaded_by")) if data.get("uploaded_by") else None,
                project=str(data.get("project")) if data.get("project") else None,
                organization=str(data.get("organization")) if data.get("organization") else None,
                created_at=str(data.get("created_at", "")),
                updated_at=str(data.get("updated_at", ""))
            )
        except Exception as e:
            print(f"Error converting image data: {e}, data: {img_data}")
            # Return a minimal valid ImageDict on error
            return ImageDict(
                filename="Unknown",
                gcp_path="",
                created_at=""
            )
    
    async def load_images(self, page: int = 1):
        """Load images with pagination"""
        self.is_loading = True
        self.current_page = page
        
        try:
            if self.search_query:
                result = await ImageRepository.search_images(
                    self.search_query, page, self.page_size
                )
            else:
                result = await ImageRepository.get_images_paginated(
                    page, self.page_size
                )
            
            # Convert to ImageDict objects with safe conversion
            image_list = []
            for img in result["images"]:
                converted_img = self._safe_convert_to_image_dict(img)
                # Generate presigned URL if gcp_path exists and doesn't already start with http
                if converted_img.gcp_path and not converted_img.gcp_path.startswith(("http://", "https://")):
                    converted_img.presigned_url = self.get_presigned_url(converted_img.gcp_path)
                else:
                    converted_img.presigned_url = converted_img.gcp_path
                image_list.append(converted_img)
            
            self.images = image_list
            self.total_count = result["total_count"]
            self.total_pages = result["total_pages"]
            self.current_page = result["page"]
            
        except Exception as e:
            print(f"Error loading images: {e}")
            import traceback
            traceback.print_exc()
            self.images = []
            self.total_count = 0
            self.total_pages = 0
            
        self.is_loading = False
    
    async def search_images(self, query: str = ""):
        """Search images by query"""
        self.search_query = query
        await self.load_images(1)
    
    def open_image_modal(self, image_dict: ImageDict):
        """Open modal with selected image"""
        self.selected_image = image_dict
        self.show_modal = True
    
    def close_modal(self):
        """Close image modal"""
        self.show_modal = False
        self.selected_image = None
    
    async def next_page(self):
        """Go to next page"""
        if self.current_page < self.total_pages:
            await self.load_images(self.current_page + 1)
    
    async def prev_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            await self.load_images(self.current_page - 1)
    
    async def go_to_page(self, page: int):
        """Go to specific page"""
        if 1 <= page <= self.total_pages:
            await self.load_images(page)
    
    def get_presigned_url(self, gcp_path: str) -> str:
        """Get presigned URL for GCP image path - now returns actual URLs"""
        if gcp_path.startswith(("http://", "https://")):
            return gcp_path
        presigned_url = presign_url(gcp_path)
        return presigned_url