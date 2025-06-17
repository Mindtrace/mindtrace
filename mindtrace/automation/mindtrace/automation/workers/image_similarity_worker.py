from typing import Dict, Any, List
from mindtrace.core import Worker


class ImageSimilarityWorker(Worker):
    """
    Worker that performs image similarity analysis.
    
    Job inputs:
    - dataset_name_in_datalake: str
    - version: str (default "lastest")
    - query_image: str or None (if provided, finds similar images to this one)
    """
    
    def run(self, job) -> Dict[str, Any]:
        pass
    
    def embedding(self, images: Any) -> Any:
        pass
    
    def similarities(self, embeddings: Any, 
                    mode: str = "query", top_k: int = 10) -> List[Dict[str, Any]]:
        pass
