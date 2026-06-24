# backend/app/services/case_service.py
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.case import Case, SeverityEnum, BreachTypeEnum, StatusEnum
from app.models.alert import Alert
from app.schemas.case import CaseCreate, CaseUpdate

def generate_case_id(db: Session) -> str:
    """
    Generate a unique human-readable case ID in the format IR-YYYYMMDD-XXXX.
    Example: IR-20260623-0001

    The sequence resets daily — the first case of each day is 0001.
    If 9999 cases are created in one day (extremely unlikely), this will fail
    gracefully with a database unique constraint error.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"IR-{today}-"

    # Count how many cases already exist for today
    count = db.query(func.count(Case.id)).filter(
        Case.id.like(f"{prefix}%")
    ).scalar()

    sequence = (count or 0) + 1
    return f"{prefix}{sequence:04d}"   # Zero-padded to 4 digits: 0001, 0042, etc.


def create_case_from_alert(
    db: Session,
    alert: Alert,
    breach_type: BreachTypeEnum,
    severity: SeverityEnum,
    title: str = None
) -> Case:
    """
    Create a new Case linked to an existing Alert.
    Called by the alerts router after storing the raw alert.
    AI enrichment (summary, MITRE, confidence) is added in Week 3.
    """
    case_id = generate_case_id(db)

    # Auto-generate a title if not provided
    if not title:
        title = f"{breach_type.value.replace('_', ' ').title()} on {alert.host}"

    case = Case(
        id=case_id,
        title=title,
        severity=severity,
        status=StatusEnum.open,
        breach_type=breach_type,
        source_host=alert.host,
        source_ip=alert.source_ip,
        alert_id=alert.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def update_case(db: Session, case_id: str, data: CaseUpdate) -> Case | None:
    """
    Partially update a case. Only updates fields that are explicitly provided.
    Returns None if case not found.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return None

    # Only update fields that were actually sent in the request
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(case, field, value)

    db.commit()
    db.refresh(case)
    return case


def get_case(db: Session, case_id: str) -> Case | None:
    return db.query(Case).filter(Case.id == case_id).first()


def list_cases(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: str = None,
    severity: str = None,
    breach_type: str = None
) -> list[Case]:
    """
    List cases with optional filtering and pagination.
    Default: 50 most recent cases, no filter.
    """
    query = db.query(Case)

    if status:
        query = query.filter(Case.status == status)
    if severity:
        query = query.filter(Case.severity == severity)
    if breach_type:
        query = query.filter(Case.breach_type == breach_type)

    return query.order_by(Case.detected_at.desc()).offset(skip).limit(limit).all()



    # Add this to backend/app/services/case_service.py

def classify_alert_basic(level: int, groups: list[str] | None) -> tuple[BreachTypeEnum, SeverityEnum]:
    """
    Rule-based classifier — placeholder until AI agent is wired in Week 3.
    Maps Wazuh level + rule groups to BreachTypeEnum + SeverityEnum.

    Wazuh levels:
      1-3:   Informational
      4-7:   Low priority
      8-11:  Medium severity
      12-14: High severity
      15:    Critical

    Returns (breach_type, severity)
    """
    groups = groups or []

    # Map severity from Wazuh level
    if level >= 15:
        severity = SeverityEnum.critical
    elif level >= 12:
        severity = SeverityEnum.high
    elif level >= 8:
        severity = SeverityEnum.medium
    else:
        severity = SeverityEnum.low

    # Map breach_type from Wazuh rule groups
    group_str = " ".join(groups).lower()

    if any(kw in group_str for kw in ["ransomware", "encrypt", "ransom"]):
        breach_type = BreachTypeEnum.ransomware
    elif any(kw in group_str for kw in ["phish", "spam", "malicious_url"]):
        breach_type = BreachTypeEnum.phishing
    elif any(kw in group_str for kw in ["exfil", "data_leak", "transfer"]):
        breach_type = BreachTypeEnum.exfiltration
    elif any(kw in group_str for kw in ["insider", "privilege", "sudo_denied"]):
        breach_type = BreachTypeEnum.insider
    else:
        # Default: most Wazuh alerts relate to unauthorized access attempts
        breach_type = BreachTypeEnum.unauthorized_access

    return breach_type, severity