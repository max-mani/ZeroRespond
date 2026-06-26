# backend/app/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class RegisterRequest(BaseModel):
    """Used by POST /auth/register to create the first admin user."""
    email:     str = Field(..., description="User email address")
    password:  str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: Optional[str] = None
    role:      str = Field("analyst", description="analyst or admin")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "manikandan@hospital.in",
                "password": "SecurePass123",
                "full_name": "Manikandan",
                "role": "admin"
            }
        }

class LoginRequest(BaseModel):
    """Used by POST /auth/login."""
    email:    str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "manikandan@hospital.in",
                "password": "SecurePass123"
            }
        }

class TokenResponse(BaseModel):
    """Returned by POST /auth/login on success."""
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int = 28800   # 8 hours in seconds

class UserOut(BaseModel):
    """Returned by GET /auth/me."""
    id:            int
    email:         str
    full_name:     Optional[str]
    role:          str
    is_active:     bool
    created_at:    datetime
    last_login_at: Optional[datetime]

    model_config = {"from_attributes": True}