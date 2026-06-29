# backend/app/schemas/playbook.py
from pydantic import BaseModel
from typing import Optional, List

class PlaybookStepOut(BaseModel):
    """One step in a playbook."""
    id:          int
    step_number: int
    title:       str
    description: str
    linux_cmd:   Optional[str]
    windows_cmd: Optional[str]
    goal:        Optional[str]
    is_blocking: bool

    model_config = {"from_attributes": True}


class PlaybookOut(BaseModel):
    """Full playbook with all steps."""
    id:          int
    attack_type: str
    name:        str
    description: Optional[str]
    steps:       List[PlaybookStepOut]

    model_config = {"from_attributes": True}


class PlaybookListItem(BaseModel):
    """Compact playbook for list view — no steps."""
    id:          int
    attack_type: str
    name:        str
    description: Optional[str]

    model_config = {"from_attributes": True}


class CaseStepOut(BaseModel):
    """Tracks completion of a playbook step for a specific case."""
    id:               int
    playbook_step_id: int
    completed_by:     Optional[str]
    completed_at:     Optional[str]
    playbook_step:    PlaybookStepOut

    model_config = {"from_attributes": True}