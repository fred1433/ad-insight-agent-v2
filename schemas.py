from pydantic import BaseModel
from typing import Optional

class Ad(BaseModel):
    id: str
    name: str
    creative_id: Optional[str] = None
    video_id: Optional[str] = None 