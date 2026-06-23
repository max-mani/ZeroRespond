# backend/app/models/case.py
import enum
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class SeverityEnum(str, enum.Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"

class StatusEnum(str, enum.Enum):
    open          = "open"
    investigating = "investigating"
    contained     = "contained"
    resolved      = "resolved"
    closed        = "closed"

class BreachTypeEnum(str, enum.Enum):
    ransomware          = "ransomware"
    phishing            = "phishing"
    unauthorized_access = "unauthorized_access"
    exfiltration        = "exfiltration"
    insider             = "insider"

class Case(Base):
    __tablename__ = "cases"

    # Identity
    id              = Column(String(30), primary_key=True)   # IR-YYYYMMDD-XXXX
    title           = Column(String(255), nullable=False)

    # Classification
    severity        = Column(Enum(SeverityEnum), nullable=False, default=SeverityEnum.medium)
    status          = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.open)
    breach_type     = Column(Enum(BreachTypeEnum), nullable=False)

    # DPDP Act 2023 Section 8(6) fields
    data_categories = Column(String(255), nullable=True)   # PII, Financial, Health, Credentials
    persons_affected= Column(Integer, nullable=True)
    breach_est_at   = Column(DateTime(timezone=True), nullable=True)  # Estimated breach start

    # Attack context
    source_host     = Column(String(255), nullable=True)
    source_ip       = Column(String(45), nullable=True)

    # Relationships
    alert_id        = Column(String(50), ForeignKey("alerts.id"), nullable=True)
    playbook_id     = Column(Integer, ForeignKey("playbooks.id"), nullable=True)
    assigned_to     = Column(String(255), nullable=True)

    # AI enrichment
    ai_summary      = Column(Text, nullable=True)
    ai_confidence   = Column(Float, nullable=True)           # 0.0 - 100.0
    ai_mitre        = Column(String(20), nullable=True)      # T1486, T1566, etc.
    immediate_action= Column(Text, nullable=True)            # AI-recommended first action

    # Responder notes
    notes           = Column(Text, nullable=True)

    # Timestamps (immutable audit trail — never update detected_at)
    detected_at     = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at     = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    playbook        = relationship("Playbook")
    alert           = relationship("Alert")
    steps           = relationship("CaseStep", back_populates="case")
    evidence        = relationship("Evidence", back_populates="case")