# backend/app/models/alert.py
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.models.base import Base

class Alert(Base):
    __tablename__ = "alerts"

    id              = Column(String(50), primary_key=True)  # wazuh alert ID
    wazuh_rule_id   = Column(Integer, nullable=False)
    level           = Column(Integer, nullable=False)        # Wazuh severity level 1-15
    description     = Column(String(500), nullable=False)
    source_ip       = Column(String(45), nullable=True)      # IPv4 or IPv6
    host            = Column(String(255), nullable=False)
    groups          = Column(JSON, nullable=True)             # ["authentication_failed", "sshd"]
    attack_type     = Column(String(50), nullable=True)      # Set after AI classification
    raw_json        = Column(JSON, nullable=False)            # Full Wazuh alert payload
    received_at     = Column(DateTime(timezone=True), server_default=func.now())