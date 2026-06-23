# backend/app/models/org_profile.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.models.base import Base

class OrgProfile(Base):
    __tablename__ = "org_profile"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(255), nullable=False)
    dpo_name        = Column(String(255), nullable=False)   # Data Protection Officer
    dpo_email       = Column(String(255), nullable=False)
    address         = Column(String(500), nullable=True)
    cert_in_email   = Column(String(255), default="incident@cert-in.org.in")
    cert_in_notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())