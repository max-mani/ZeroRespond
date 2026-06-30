# backend/app/schemas/evidence.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EvidenceOut(BaseModel):
    """Returned by GET /cases/{id}/evidence and POST /cases/{id}/evidence."""
    id:          int
    case_id:     str
    filename:    str
    description: Optional[str]
    file_size:   Optional[int]
    uploaded_by: Optional[str]
    uploaded_at: datetime

    model_config = {"from_attributes": True}