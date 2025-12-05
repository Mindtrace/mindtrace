from dataclasses import dataclass
from typing import Optional

@dataclass
class Plant:
    id: str
    name: str
    location: Optional[str] = None
