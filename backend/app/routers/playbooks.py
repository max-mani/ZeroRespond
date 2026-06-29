# backend/app/routers/playbooks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app.models.playbook import Playbook, PlaybookStep
from app.models.case import Case
from app.models.case_step import CaseStep
from app.schemas.playbook import PlaybookOut, PlaybookListItem, CaseStepOut
from app.services.auth_service import get_current_user
from app.models.user import User

router = APIRouter(prefix="/playbooks", tags=["Playbooks"])


@router.get(
    "",
    response_model=List[PlaybookListItem],
    summary="List all playbooks (one per breach type)"
)
def list_playbooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Playbook]:
    return db.query(Playbook).order_by(Playbook.attack_type).all()


@router.get(
    "/{attack_type}",
    response_model=PlaybookOut,
    summary="Get full playbook with steps for a breach type",
    description="attack_type must be one of: ransomware, phishing, unauthorized_access, exfiltration, insider"
)
def get_playbook(
    attack_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Playbook:
    playbook = db.query(Playbook).filter(Playbook.attack_type == attack_type).first()
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No playbook found for attack type '{attack_type}'. "
                   f"Valid types: ransomware, phishing, unauthorized_access, exfiltration, insider"
        )
    return playbook


# ─── Case-specific playbook endpoints ─────────────────────────────────────────

cases_router = APIRouter(prefix="/cases", tags=["Playbooks"])


@cases_router.get(
    "/{case_id}/playbook",
    response_model=PlaybookOut,
    summary="Get the playbook for a specific case based on its breach type"
)
def get_case_playbook(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Playbook:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )

    playbook = db.query(Playbook).filter(
        Playbook.attack_type == case.breach_type.value
    ).first()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No playbook found for breach type '{case.breach_type.value}'"
        )
    return playbook


@cases_router.post(
    "/{case_id}/steps/{step_id}/complete",
    response_model=CaseStepOut,
    summary="Mark a playbook step as completed for a case"
)
def complete_step(
    case_id: str,
    step_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CaseStep:
    # Verify case exists
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Verify step exists
    step = db.query(PlaybookStep).filter(PlaybookStep.id == step_id).first()
    if not step:
        raise HTTPException(status_code=404, detail=f"Playbook step {step_id} not found")

    # Check if already completed
    existing = db.query(CaseStep).filter(
        CaseStep.case_id == case_id,
        CaseStep.playbook_step_id == step_id
    ).first()

    if existing:
        return existing   # Idempotent — return existing completion record

    # Create completion record
    case_step = CaseStep(
        case_id=case_id,
        playbook_step_id=step_id,
        completed_by=current_user.email,
        completed_at=datetime.now(timezone.utc)
    )
    db.add(case_step)
    db.commit()
    db.refresh(case_step)
    return case_step