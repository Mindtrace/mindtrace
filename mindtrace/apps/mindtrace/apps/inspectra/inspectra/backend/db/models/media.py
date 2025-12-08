from datetime import datetime, timezone
from typing import Any, Dict, Optional

from inspectra.backend.db.models.enums import MediaKind
from pydantic import Field

from mindtrace.database import MindtraceDocument


class Media(MindtraceDocument):
    kind: MediaKind
    uri: str  # relative/path to the media file within the media storage bucket
    hash: Optional[str] = None  # hash of the media file
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    meta: Dict[str, Any] = Field(default_factory=dict)
