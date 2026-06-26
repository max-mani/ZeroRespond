# backend/app/routers/alerts.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertCreate, AlertOut
from app.schemas.case import CaseDetail
from app.services.case_service import create_case_from_alert, classify_alert_basic
from app.services.alert_queue import enqueue_alert

from app.services.auth_service import get_current_user

router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"],
    dependencies=[Depends(get_current_user)] 
)

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a Wazuh alert and create an incident case",
    description="""
    Ingests a Wazuh alert and immediately creates an incident case.

    What this endpoint does:
    1. Validates the incoming JSON
    2. Checks for duplicate alert ID (idempotent)
    3. Stores the raw alert in the alerts table
    4. Creates a case using rule-based classification (instant response)
    5. Enqueues the alert for async AI enrichment (non-blocking)
    6. Returns the case immediately — AI fields are populated within seconds

    The case is returned before AI enrichment is complete.
    Poll GET /cases/{id} to get the enriched case with AI summary and MITRE technique.
    """
)
async def ingest_alert(
    payload: AlertCreate,
    db: Session = Depends(get_db)
) -> CaseDetail:

    # Step 1: Duplicate check
    existing = db.query(Alert).filter(Alert.id == payload.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert {payload.id} already ingested. Duplicate ignored."
        )

    # Step 2: Store the raw alert
    alert = Alert(
        id=payload.id,
        wazuh_rule_id=payload.wazuh_rule_id,
        level=payload.level,
        description=payload.description,
        source_ip=payload.source_ip,
        host=payload.host,
        groups=payload.groups,
        raw_json=payload.raw_json,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Step 3: Rule-based classification for immediate case creation
    # This runs in < 1ms and gives the case a valid breach_type and severity instantly.
    # The AI agent will override these values once it finishes async enrichment.
    breach_type, severity = classify_alert_basic(alert.level, alert.groups)

    # Step 4: Create the case
    case = create_case_from_alert(
        db=db,
        alert=alert,
        breach_type=breach_type,
        severity=severity
    )

    # Step 5: Enqueue for async AI enrichment (non-blocking — returns immediately)
    await enqueue_alert(alert.id, alert.level)

    return case


@router.get(
    "",
    response_model=List[AlertOut],
    summary="List all ingested alerts"
)
def list_alerts(
    skip: int = 0,
    limit: int = 50,
    host: Optional[str] = None,
    db: Session = Depends(get_db)
) -> List[Alert]:
    query = db.query(Alert)
    if host:
        query = query.filter(Alert.host == host)
    return query.order_by(Alert.received_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{alert_id}",
    response_model=AlertOut,
    summary="Get a single alert by ID"
)
def get_alert(alert_id: str, db: Session = Depends(get_db)) -> Alert:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found"
        )
    return alert