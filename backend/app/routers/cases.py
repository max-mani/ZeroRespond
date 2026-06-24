# backend/app/routers/cases.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.case import CaseCreate, CaseUpdate, CaseListItem, CaseDetail
from app.services.case_service import (
    create_case_from_alert,
    update_case,
    get_case,
    list_cases,
    generate_case_id,
)
from app.models.case import Case, SeverityEnum, StatusEnum, BreachTypeEnum

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get(
    "",
    response_model=List[CaseListItem],
    summary="List all incident cases",
    description="Returns cases ordered by detection time (newest first). Supports filtering by status, severity, and breach type."
)
def get_cases(
    skip:         int = Query(0, ge=0, description="Pagination offset"),
    limit:        int = Query(50, ge=1, le=200, description="Max results"),
    status:       Optional[StatusEnum]      = Query(None, description="Filter by case status"),
    severity:     Optional[SeverityEnum]    = Query(None, description="Filter by severity"),
    breach_type:  Optional[BreachTypeEnum]  = Query(None, description="Filter by breach type"),
    db: Session = Depends(get_db)
) -> List[Case]:

    return list_cases(
        db=db,
        skip=skip,
        limit=limit,
        status=status.value if status else None,
        severity=severity.value if severity else None,
        breach_type=breach_type.value if breach_type else None
    )


@router.get(
    "/{case_id}",
    response_model=CaseDetail,
    summary="Get full case detail"
)
def get_case_detail(case_id: str, db: Session = Depends(get_db)) -> Case:
    case = get_case(db, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    return case


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CaseDetail,
    summary="Manually create an incident case",
    description="For cases not triggered by an alert — manual entry by a responder."
)
def create_case_manual(
    payload: CaseCreate,
    db: Session = Depends(get_db)
) -> Case:
    case_id = generate_case_id(db)
    case = Case(
        id=case_id,
        title=payload.title,
        severity=payload.severity,
        status=StatusEnum.open,
        breach_type=payload.breach_type,
        data_categories=payload.data_categories,
        persons_affected=payload.persons_affected,
        source_host=payload.source_host,
        source_ip=payload.source_ip,
        alert_id=payload.alert_id,
        assigned_to=payload.assigned_to,
        notes=payload.notes,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.patch(
    "/{case_id}",
    response_model=CaseDetail,
    summary="Update a case (partial update)",
    description="""
    Update one or more fields on an existing case.
    Only fields you include in the request body are changed.
    Common uses:
    - Change status: open → investigating → contained → resolved → closed
    - Add responder notes
    - Set assigned_to for case ownership
    - Record persons_affected for DPDP reporting
    """
)
def patch_case(
    case_id: str,
    payload: CaseUpdate,
    db: Session = Depends(get_db)
) -> Case:
    case = update_case(db, case_id, payload)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    return case


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a case",
    description="Hard delete. Only use in development. In production, close cases instead of deleting."
)
def delete_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    db.delete(case)
    db.commit()

# Add to backend/app/routers/cases.py

from app.services.alert_queue import enqueue_alert
from app.models.alert import Alert

@router.post(
    "/{case_id}/re-enrich",
    response_model=CaseDetail,
    summary="Re-run AI enrichment on an existing case",
    description="Queues the linked alert for re-processing by the AI agent. Useful after prompt updates or model changes."
)
async def re_enrich_case(case_id: str, db: Session = Depends(get_db)) -> Case:
    case = get_case(db, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    if not case.alert_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case {case_id} has no linked alert — cannot re-enrich"
        )

    alert = db.query(Alert).filter(Alert.id == case.alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Linked alert {case.alert_id} not found"
        )

    await enqueue_alert(alert.id, alert.level)
    return case