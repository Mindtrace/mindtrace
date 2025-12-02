from dataclasses import dataclass
from typing import Optional

@dataclass
class Role:
    id: str
    name: str
    description: Optional[str] = None
    permissions: Optional[list[str]] = None
