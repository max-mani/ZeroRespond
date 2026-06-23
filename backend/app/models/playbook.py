# backend/app/models/playbook.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base

class Playbook(Base):
    __tablename__ = "playbooks"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    attack_type = Column(String(50), unique=True, nullable=False)  # must match Case.breach_type
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    steps       = relationship("PlaybookStep", back_populates="playbook",
                               order_by="PlaybookStep.step_number")


class PlaybookStep(Base):
    __tablename__ = "playbook_steps"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)     # What to do and why
    linux_cmd   = Column(Text, nullable=True)      # Exact Linux command
    windows_cmd = Column(Text, nullable=True)      # Exact Windows PowerShell command
    goal        = Column(String(255), nullable=True) # What this step achieves
    is_blocking = Column(Boolean, default=False)   # Must complete before next step

    playbook    = relationship("Playbook", back_populates="steps")