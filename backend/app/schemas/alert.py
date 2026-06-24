# backend/app/schemas/alert.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any, Dict

# ─── Input: What Wazuh sends us ───────────────────────────────────────────────

class AlertCreate(BaseModel):
    """
    Shape of the JSON payload Wazuh (or the alert-processor) sends to POST /alerts.
    All fields map directly to what a Wazuh webhook delivers.
    """
    id:             str         = Field(...,  description="Wazuh alert ID (unique)")
    wazuh_rule_id:  int         = Field(...,  description="Wazuh rule that fired")
    level:          int         = Field(...,  ge=1, le=15, description="Severity 1-15")
    description:    str         = Field(...,  max_length=500)
    source_ip:      Optional[str] = Field(None, description="Attacker IP or None")
    host:           str         = Field(...,  description="Affected hostname")
    groups:         Optional[List[str]] = Field(None, description="Wazuh rule groups")
    raw_json:       Dict[str, Any] = Field(..., description="Full Wazuh alert payload")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "1750123456.88321",
                "wazuh_rule_id": 5710,
                "level": 12,
                "description": "SSH brute force — multiple authentication failures",
                "source_ip": "203.0.113.42",
                "host": "webserver01",
                "groups": ["authentication_failed", "sshd"],
                "raw_json": {
                    "rule_id": "5710",
                    "level": 12,
                    "description": "SSH brute force",
                    "source_ip": "203.0.113.42",
                    "host": "webserver01",
                    "timestamp": "2026-06-23T10:15:30Z"
                }
            }
        }

# ─── Output: What we return when someone reads an alert ───────────────────────

class AlertOut(BaseModel):
    """Returned by GET /alerts and GET /alerts/{id}"""
    id:             str
    wazuh_rule_id:  int
    level:          int
    description:    str
    source_ip:      Optional[str]
    host:           str
    groups:         Optional[List[str]]
    attack_type:    Optional[str]       # Set after AI classification (Week 3)
    received_at:    datetime

    model_config = {"from_attributes": True}  # Allows ORM → Pydantic conversion