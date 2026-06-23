# backend/app/models/case_step.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class CaseStep(Base):
    __tablename__ = "case_steps"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    case_id          = Column(String(30), ForeignKey("cases.id"), nullable=False)
    playbook_step_id = Column(Integer, ForeignKey("playbook_steps.id"), nullable=False)
    completed_by     = Column(String(255), nullable=True)
    completed_at     = Column(DateTime(timezone=True), nullable=True)

    case             = relationship("Case", back_populates="steps")
    playbook_step    = relationship("PlaybookStep")