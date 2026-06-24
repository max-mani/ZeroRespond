# backend/app/schemas/case.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.case import SeverityEnum, StatusEnum, BreachTypeEnum

# ─── Input: Creating a case manually (not from an alert) ──────────────────────

class CaseCreate(BaseModel):
    """
    Used when a responder manually creates a case (no alert source).
    All AI fields are optional — they get filled later.
    """
    title:            str          = Field(..., min_length=5, max_length=255)
    severity:         SeverityEnum = Field(SeverityEnum.medium)
    breach_type:      BreachTypeEnum
    data_categories:  Optional[str] = Field(None, description="PII, Financial, Health, Credentials — comma-separated")
    persons_affected: Optional[int] = Field(None, ge=0)
    source_host:      Optional[str] = None
    source_ip:        Optional[str] = None
    alert_id:         Optional[str] = None     # Link to an existing alert
    assigned_to:      Optional[str] = None
    notes:            Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "title": "SSH Brute Force on webserver01",
                "severity": "high",
                "breach_type": "unauthorized_access",
                "data_categories": "Credentials",
                "persons_affected": 0,
                "source_host": "webserver01",
                "source_ip": "203.0.113.42",
                "assigned_to": "manikandan@zerorespondnd.in"
            }
        }

# ─── Input: Updating a case (partial update) ──────────────────────────────────

class CaseUpdate(BaseModel):
    """
    Used by PATCH /cases/{id}. Every field is Optional.
    A responder might only want to update status or add notes.
    """
    status:           Optional[StatusEnum]   = None
    severity:         Optional[SeverityEnum] = None
    assigned_to:      Optional[str]          = None
    notes:            Optional[str]          = None
    data_categories:  Optional[str]          = None
    persons_affected: Optional[int]          = Field(None, ge=0)
    resolved_at:      Optional[datetime]     = None

# ─── Output: What we return for a case in a list ─────────────────────────────

class CaseListItem(BaseModel):
    """
    Compact representation for GET /cases (list view).
    Does not include AI summary or notes — keeps responses small.
    """
    id:               str
    title:            str
    severity:         SeverityEnum
    status:           StatusEnum
    breach_type:      BreachTypeEnum
    source_ip:        Optional[str]
    source_host:      Optional[str]
    assigned_to:      Optional[str]
    ai_confidence:    Optional[float]
    detected_at:      datetime

    model_config = {"from_attributes": True}

# ─── Output: Full case detail ─────────────────────────────────────────────────

class CaseDetail(BaseModel):
    """
    Full representation for GET /cases/{id}.
    Includes AI fields, notes, DPDP fields.
    """
    id:               str
    title:            str
    severity:         SeverityEnum
    status:           StatusEnum
    breach_type:      BreachTypeEnum
    data_categories:  Optional[str]
    persons_affected: Optional[int]
    breach_est_at:    Optional[datetime]
    source_host:      Optional[str]
    source_ip:        Optional[str]
    alert_id:         Optional[str]
    playbook_id:      Optional[int]
    assigned_to:      Optional[str]
    ai_summary:       Optional[str]
    ai_confidence:    Optional[float]
    ai_mitre:         Optional[str]
    immediate_action: Optional[str]
    notes:            Optional[str]
    detected_at:      datetime
    resolved_at:      Optional[datetime]
    created_at:       datetime
    updated_at:       Optional[datetime]

    model_config = {"from_attributes": True}