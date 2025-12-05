from dataclasses import dataclass
from typing import Optional

@dataclass
class Line:
    id: str
    name: str
    plant_id: Optional[str] = None
