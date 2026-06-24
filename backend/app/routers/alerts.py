# backend/app/routers/alerts.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertCreate, AlertOut
from app.schemas.case import CaseDetail
from app.services.case_service import create_case_from_alert, classify_alert_basic

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a Wazuh alert and create an incident case",
    description="""
    This is the main entry point for alert ingestion.
    Called by the alert-processor service when Wazuh fires an alert.

    What this endpoint does:
    1. Validates the incoming JSON against AlertCreate schema
    2. Checks for duplicate alert ID (idempotent — safe to retry)
    3. Stores the raw alert in the alerts table
    4. Classifies breach_type and severity using rule-based logic (AI in Week 3)
    5. Creates an incident case linked to this alert
    6. Returns the created case

    Severity mapping:
    - Wazuh level 15    → critical
    - Wazuh level 12-14 → high
    - Wazuh level 8-11  → medium
    - Wazuh level 1-7   → low
    """
)
def ingest_alert(
    payload: AlertCreate,
    db: Session = Depends(get_db)
) -> CaseDetail:

    # Step 1: Check for duplicate (Wazuh can retry webhook deliveries)
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

    # Step 3: Classify alert (rule-based for now, AI replaces this in Week 3)
    breach_type, severity = classify_alert_basic(alert.level, alert.groups)

    # Step 4: Create incident case
    case = create_case_from_alert(
        db=db,
        alert=alert,
        breach_type=breach_type,
        severity=severity
    )

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