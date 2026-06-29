# backend/app/schemas/org.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class OrgProfileOut(BaseModel):
    """Returned by GET /org."""
    id:                  int
    name:                str
    dpo_name:            str
    dpo_email:           str
    address:             Optional[str]
    cert_in_email:       str
    cert_in_notified_at: Optional[datetime]
    created_at:          datetime
    updated_at:          Optional[datetime]

    model_config = {"from_attributes": True}


class OrgProfileUpdate(BaseModel):
    """
    Used by PUT /org to update org details.
    All fields are optional — send only what you want to change.
    """
    name:          Optional[str] = Field(None, min_length=2, max_length=255)
    dpo_name:      Optional[str] = Field(None, min_length=2, max_length=255)
    dpo_email:     Optional[str] = Field(None, max_length=255)
    address:       Optional[str] = Field(None, max_length=500)
    cert_in_email: Optional[str] = Field(None, max_length=255)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Coimbatore Medical College Hospital",
                "dpo_name": "Dr. Manikandan",
                "dpo_email": "dpo@cmch.edu.in",
                "address": "Coimbatore, Tamil Nadu 641 014",
                "cert_in_email": "incident@cert-in.org.in"
            }
        }