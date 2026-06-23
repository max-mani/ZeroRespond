# backend/app/models/evidence.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class Evidence(Base):
    __tablename__ = "evidence"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    case_id     = Column(String(30), ForeignKey("cases.id"), nullable=False)
    filename    = Column(String(255), nullable=False)    # Original filename
    filepath    = Column(String(500), nullable=False)    # Path on disk
    description = Column(Text, nullable=True)            # What this file shows
    file_size   = Column(Integer, nullable=True)         # Bytes
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    case        = relationship("Case", back_populates="evidence")