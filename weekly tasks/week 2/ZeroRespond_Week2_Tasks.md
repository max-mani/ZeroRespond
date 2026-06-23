# ZeroRespond — Week 2 Task List
**Phase 2 · Case Manager REST API · Pydantic Schemas + CRUD Endpoints + Alert Ingestion**

> **Goal by end of Week 2:** A fully working REST API for cases and alerts. You can `POST /alerts` to receive a Wazuh alert, store it in PostgreSQL, and create an incident case from it. You can `GET /cases` to list all cases. Every endpoint is tested and documented in Swagger. No frontend, no AI yet — just clean, correct API logic you will build everything else on.

---

## What you have coming in from Week 1

- PostgreSQL running in Docker with all 7 tables migrated
- `backend/app/models/` — all 7 SQLAlchemy models (Case, Alert, Playbook, PlaybookStep, CaseStep, Evidence, OrgProfile)
- `backend/app/services/ollama_client.py` — Ollama client with JSON parsing
- `backend/app/main.py` — FastAPI skeleton with CORS and `/health`
- `backend/app/config.py` — pydantic-settings reading from `.env`
- `backend/app/database.py` — SQLAlchemy engine and `get_db()` dependency

---

## Week 2 Architecture

```
POST /alerts          → store alert → create case → return case ID
GET  /cases           → list all cases (paginated, filterable)
GET  /cases/{id}      → get one case with full detail
PATCH /cases/{id}     → update case (status, notes, assigned_to)
GET  /alerts          → list all alerts
GET  /alerts/{id}     → get one alert with raw JSON

Folder structure to build this week:
backend/app/
├── schemas/
│   ├── alert.py       ← Pydantic input/output models for alerts
│   └── case.py        ← Pydantic input/output models for cases
├── routers/
│   ├── alerts.py      ← POST /alerts, GET /alerts, GET /alerts/{id}
│   └── cases.py       ← GET /cases, GET /cases/{id}, PATCH /cases/{id}
└── services/
    └── case_service.py ← business logic: create case from alert, generate case ID
```

---

## Day 1 — Pydantic Schemas for Alerts

Schemas are the contract between your API and the outside world. They define what data comes in and what goes out. Write these before any router code.

---

### Task 1.1 — Understand why schemas are separate from models

SQLAlchemy models (`app/models/`) represent database tables.
Pydantic schemas (`app/schemas/`) represent API request/response shapes.

They are different because:
- The DB model has columns you never expose in the API (e.g. `raw_json`, `filepath`)
- The API accepts data that doesn't map 1:1 to the DB (e.g. a Wazuh webhook payload)
- You need different shapes for input (create) vs output (read)

Rule: **never return a SQLAlchemy model directly from a FastAPI endpoint**. Always go through a Pydantic schema.

---

### Task 1.2 — Create backend/app/schemas/alert.py

```python
# backend/app/schemas/alert.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any, Dict

# ─── Input: What Wazuh sends us ───────────────────────────────────────────────

class AlertCreate(BaseModel):
    """
    Shape of the JSON payload Wazuh (or the alert-processor) sends to POST /alerts.
    All fields map directly to what a Wazuh webhook delivers.
    """
    id:             str         = Field(...,  description="Wazuh alert ID (unique)")
    wazuh_rule_id:  int         = Field(...,  description="Wazuh rule that fired")
    level:          int         = Field(...,  ge=1, le=15, description="Severity 1-15")
    description:    str         = Field(...,  max_length=500)
    source_ip:      Optional[str] = Field(None, description="Attacker IP or None")
    host:           str         = Field(...,  description="Affected hostname")
    groups:         Optional[List[str]] = Field(None, description="Wazuh rule groups")
    raw_json:       Dict[str, Any] = Field(..., description="Full Wazuh alert payload")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "1750123456.88321",
                "wazuh_rule_id": 5710,
                "level": 12,
                "description": "SSH brute force — multiple authentication failures",
                "source_ip": "203.0.113.42",
                "host": "webserver01",
                "groups": ["authentication_failed", "sshd"],
                "raw_json": {
                    "rule_id": "5710",
                    "level": 12,
                    "description": "SSH brute force",
                    "source_ip": "203.0.113.42",
                    "host": "webserver01",
                    "timestamp": "2026-06-23T10:15:30Z"
                }
            }
        }

# ─── Output: What we return when someone reads an alert ───────────────────────

class AlertOut(BaseModel):
    """Returned by GET /alerts and GET /alerts/{id}"""
    id:             str
    wazuh_rule_id:  int
    level:          int
    description:    str
    source_ip:      Optional[str]
    host:           str
    groups:         Optional[List[str]]
    attack_type:    Optional[str]       # Set after AI classification (Week 3)
    received_at:    datetime

    model_config = {"from_attributes": True}  # Allows ORM → Pydantic conversion
```

> **Why no `raw_json` in `AlertOut`?** The raw Wazuh payload can be very large. We store it in the DB for forensics but never need to send it in a list response. We will add a separate `AlertDetail` schema in a later week if needed.

---

### Task 1.3 — Create backend/app/schemas/case.py

```python
# backend/app/schemas/case.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.case import SeverityEnum, StatusEnum, BreachTypeEnum

# ─── Input: Creating a case manually (not from an alert) ──────────────────────

class CaseCreate(BaseModel):
    """
    Used when a responder manually creates a case (no alert source).
    All AI fields are optional — they get filled later.
    """
    title:            str          = Field(..., min_length=5, max_length=255)
    severity:         SeverityEnum = Field(SeverityEnum.medium)
    breach_type:      BreachTypeEnum
    data_categories:  Optional[str] = Field(None, description="PII, Financial, Health, Credentials — comma-separated")
    persons_affected: Optional[int] = Field(None, ge=0)
    source_host:      Optional[str] = None
    source_ip:        Optional[str] = None
    alert_id:         Optional[str] = None     # Link to an existing alert
    assigned_to:      Optional[str] = None
    notes:            Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "title": "SSH Brute Force on webserver01",
                "severity": "high",
                "breach_type": "unauthorized_access",
                "data_categories": "Credentials",
                "persons_affected": 0,
                "source_host": "webserver01",
                "source_ip": "203.0.113.42",
                "assigned_to": "manikandan@zerorespondnd.in"
            }
        }

# ─── Input: Updating a case (partial update) ──────────────────────────────────

class CaseUpdate(BaseModel):
    """
    Used by PATCH /cases/{id}. Every field is Optional.
    A responder might only want to update status or add notes.
    """
    status:           Optional[StatusEnum]   = None
    severity:         Optional[SeverityEnum] = None
    assigned_to:      Optional[str]          = None
    notes:            Optional[str]          = None
    data_categories:  Optional[str]          = None
    persons_affected: Optional[int]          = Field(None, ge=0)
    resolved_at:      Optional[datetime]     = None

# ─── Output: What we return for a case in a list ─────────────────────────────

class CaseListItem(BaseModel):
    """
    Compact representation for GET /cases (list view).
    Does not include AI summary or notes — keeps responses small.
    """
    id:               str
    title:            str
    severity:         SeverityEnum
    status:           StatusEnum
    breach_type:      BreachTypeEnum
    source_ip:        Optional[str]
    source_host:      Optional[str]
    assigned_to:      Optional[str]
    ai_confidence:    Optional[float]
    detected_at:      datetime

    model_config = {"from_attributes": True}

# ─── Output: Full case detail ─────────────────────────────────────────────────

class CaseDetail(BaseModel):
    """
    Full representation for GET /cases/{id}.
    Includes AI fields, notes, DPDP fields.
    """
    id:               str
    title:            str
    severity:         SeverityEnum
    status:           StatusEnum
    breach_type:      BreachTypeEnum
    data_categories:  Optional[str]
    persons_affected: Optional[int]
    breach_est_at:    Optional[datetime]
    source_host:      Optional[str]
    source_ip:        Optional[str]
    alert_id:         Optional[str]
    playbook_id:      Optional[int]
    assigned_to:      Optional[str]
    ai_summary:       Optional[str]
    ai_confidence:    Optional[float]
    ai_mitre:         Optional[str]
    immediate_action: Optional[str]
    notes:            Optional[str]
    detected_at:      datetime
    resolved_at:      Optional[datetime]
    created_at:       datetime
    updated_at:       Optional[datetime]

    model_config = {"from_attributes": True}
```

Commit:
```bash
git add backend/app/schemas/
git commit -m "feat: pydantic schemas for alerts and cases (create, update, list, detail)"
```

---

## Day 2 — Case ID Generator + Case Service

The Case ID (`IR-YYYYMMDD-XXXX`) is not auto-generated by the database. You generate it in Python before writing to the DB. This is intentional — it makes the ID human-readable and DPDP-traceable.

---

### Task 2.1 — Create backend/app/services/case_service.py

```python
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
```

---

### Task 2.2 — Understand the alert-to-case mapping

When a Wazuh alert arrives, we need to decide its `breach_type` and `severity` for the case. In Week 3, the AI agent will do this classification. For now, write a simple **rule-based mapper** as a placeholder. This is how you build incrementally — placeholder logic now, AI later.

```python
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
```

Commit:
```bash
git add backend/app/services/case_service.py
git commit -m "feat: case service — ID generator, create from alert, update, rule-based classifier"
```

---

## Day 3 — Alerts Router

### Task 3.1 — Create backend/app/routers/alerts.py

```python
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
```

---

### Task 3.2 — Register the alerts router in main.py

Open `backend/app/main.py` and update it:

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import alerts, cases   # import routers

app = FastAPI(
    title="ZeroRespond API",
    description="AI-Enhanced Incident Response Platform — DPDP Compliant",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(alerts.router)
app.include_router(cases.router)

@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": "development"
    }
```

> Note: This will fail until you create `routers/cases.py` in Day 4. Create a stub for now:

```python
# backend/app/routers/cases.py  (stub — full version Day 4)
from fastapi import APIRouter
router = APIRouter(prefix="/cases", tags=["Cases"])
```

Commit:
```bash
git add backend/app/routers/ backend/app/main.py
git commit -m "feat: alerts router — POST /alerts, GET /alerts, GET /alerts/{id}"
```

---

### Task 3.3 — Test the alerts endpoint manually

Start the server:
```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload
```

Send a test alert with curl:
```bash
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "id": "1750123456.88321",
    "wazuh_rule_id": 5710,
    "level": 12,
    "description": "SSH brute force — multiple authentication failures",
    "source_ip": "203.0.113.42",
    "host": "webserver01",
    "groups": ["authentication_failed", "sshd"],
    "raw_json": {
      "rule_id": "5710",
      "level": 12,
      "description": "SSH brute force",
      "source_ip": "203.0.113.42",
      "host": "webserver01",
      "timestamp": "2026-06-23T10:15:30Z"
    }
  }'
```

Expected response (HTTP 201):
```json
{
  "id": "IR-20260623-0001",
  "title": "Unauthorized Access on webserver01",
  "severity": "high",
  "status": "open",
  "breach_type": "unauthorized_access",
  "source_ip": "203.0.113.42",
  "source_host": "webserver01",
  "alert_id": "1750123456.88321",
  ...
}
```

Test duplicate rejection:
```bash
# Send the same alert again — should return 409
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{ "id": "1750123456.88321", ... same payload ... }'
# Expected: {"detail": "Alert 1750123456.88321 already ingested. Duplicate ignored."}
```

Verify data in PostgreSQL:
```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, wazuh_rule_id, level, host, attack_type FROM alerts;"

docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, title, severity, status, breach_type, alert_id FROM cases;"
```

---

## Day 4 — Cases Router

### Task 4.1 — Create backend/app/routers/cases.py (full version)

```python
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
```

Commit:
```bash
git add backend/app/routers/cases.py
git commit -m "feat: cases router — GET /cases, GET /cases/{id}, POST /cases, PATCH /cases/{id}"
```

---

### Task 4.2 — Test all case endpoints

```bash
# List all cases (should show the case from Day 3)
curl http://localhost:8000/cases

# Get a specific case
curl http://localhost:8000/cases/IR-20260623-0001

# Filter by severity
curl "http://localhost:8000/cases?severity=high"

# Filter by status
curl "http://localhost:8000/cases?status=open"

# Manually create a case
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Phishing email targeting finance team",
    "severity": "high",
    "breach_type": "phishing",
    "data_categories": "Credentials, PII",
    "persons_affected": 12,
    "assigned_to": "manikandan@org.in"
  }'

# Update case status to investigating
curl -X PATCH http://localhost:8000/cases/IR-20260623-0001 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "investigating",
    "assigned_to": "manikandan@org.in",
    "notes": "Blocked the source IP at firewall. Investigating affected host."
  }'

# Verify update in DB
curl http://localhost:8000/cases/IR-20260623-0001
```

---

## Day 5 — Error Handling + Validation

Good APIs fail clearly. Right now, if you send invalid data, FastAPI gives generic errors. This day adds proper error handling throughout.

---

### Task 5.1 — Add global exception handlers to main.py

```python
# Add to backend/app/main.py (after the middleware block)
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Return a clean, structured error when Pydantic validation fails.
    Default FastAPI errors are verbose and hard to parse.
    """
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "detail": errors
        }
    )

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    """
    Return a clean error when a DB constraint is violated
    (e.g. duplicate primary key, FK violation).
    """
    return JSONResponse(
        status_code=409,
        content={
            "error": "Database constraint violation",
            "detail": str(exc.orig)
        }
    )
```

---

### Task 5.2 — Add field-level validation to schemas

Update `backend/app/schemas/case.py` to add tighter validation:

```python
# Add these validators to CaseCreate in schemas/case.py
from pydantic import field_validator
import re

class CaseCreate(BaseModel):
    # ... existing fields ...

    @field_validator("source_ip")
    @classmethod
    def validate_ip(cls, v):
        """Allow None, IPv4, or IPv6. Reject obviously wrong values."""
        if v is None:
            return v
        # Basic IP format check (does not validate all edge cases — good enough for now)
        ipv4 = re.match(r"^\d{1,3}(\.\d{1,3}){3}$", v)
        ipv6 = ":" in v
        if not ipv4 and not ipv6:
            raise ValueError(f"'{v}' is not a valid IP address format")
        return v

    @field_validator("data_categories")
    @classmethod
    def validate_data_categories(cls, v):
        """
        Ensure data_categories only contains known DPDP category names.
        This matters for DPDP Act 2023 compliance.
        """
        if v is None:
            return v
        allowed = {"PII", "Financial", "Health", "Credentials", "Biometric", "Children"}
        submitted = {cat.strip() for cat in v.split(",")}
        unknown = submitted - allowed
        if unknown:
            raise ValueError(
                f"Unknown data categories: {unknown}. "
                f"Allowed: {allowed}"
            )
        return v
```

---

### Task 5.3 — Test validation errors

```bash
# Test: missing required field
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"title": "Test"}'
# Expected: 422 with clear field-level error for missing breach_type

# Test: invalid severity value
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "breach_type": "ransomware", "severity": "extreme"}'
# Expected: 422 — "extreme" is not a valid SeverityEnum value

# Test: invalid IP address
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "breach_type": "phishing", "source_ip": "not-an-ip"}'
# Expected: 422 — source_ip validation error

# Test: invalid data category
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "breach_type": "phishing", "data_categories": "CreditCards"}'
# Expected: 422 — "CreditCards" not in allowed set

# Test: case not found
curl http://localhost:8000/cases/IR-99991231-9999
# Expected: 404 {"detail": "Case IR-99991231-9999 not found"}
```

Commit:
```bash
git add backend/app/main.py backend/app/schemas/
git commit -m "feat: global exception handlers, field validators for IP and DPDP data categories"
```

---

## Day 6 — Seed Data + Swagger Verification

### Task 6.1 — Write a seed script for development

You need sample data to work with during development. The seed script creates 5 alerts and 5 cases representing all 5 breach types, so you have something to see in the frontend next week.

Create `backend/scripts/seed_data.py`:

```python
#!/usr/bin/env python3
# backend/scripts/seed_data.py
"""
Run this to populate the database with sample cases and alerts for development.
Usage: cd backend && python scripts/seed_data.py
WARNING: Clears all existing cases and alerts before seeding. Dev only.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.case import Case, SeverityEnum, StatusEnum, BreachTypeEnum
from datetime import datetime, timezone, timedelta

def seed():
    db = SessionLocal()
    try:
        # Clear existing data (dev only!)
        db.query(Case).delete()
        db.query(Alert).delete()
        db.commit()
        print("Cleared existing cases and alerts.")

        # --- Sample Alerts ---
        alerts = [
            Alert(id="seed-alert-001", wazuh_rule_id=5710, level=12,
                  description="SSH brute force — 500 failed logins in 2 minutes",
                  source_ip="203.0.113.42", host="webserver01",
                  groups=["authentication_failed", "sshd"],
                  raw_json={"rule_id": "5710", "level": 12, "host": "webserver01"}),

            Alert(id="seed-alert-002", wazuh_rule_id=87105, level=14,
                  description="Malicious URL detected in email attachment",
                  source_ip="198.51.100.7", host="workstation-finance-03",
                  groups=["phish", "malicious_url"],
                  raw_json={"rule_id": "87105", "level": 14, "host": "workstation-finance-03"}),

            Alert(id="seed-alert-003", wazuh_rule_id=92001, level=15,
                  description="Ransomware signature detected — files being encrypted",
                  source_ip=None, host="fileserver01",
                  groups=["ransomware", "encrypt"],
                  raw_json={"rule_id": "92001", "level": 15, "host": "fileserver01"}),

            Alert(id="seed-alert-004", wazuh_rule_id=61002, level=10,
                  description="Large outbound data transfer detected — potential exfiltration",
                  source_ip="10.0.0.45", host="db-server-01",
                  groups=["exfil", "data_leak"],
                  raw_json={"rule_id": "61002", "level": 10, "host": "db-server-01"}),

            Alert(id="seed-alert-005", wazuh_rule_id=40111, level=9,
                  description="Privileged account access outside business hours",
                  source_ip="10.0.0.12", host="hr-workstation-02",
                  groups=["insider", "privilege"],
                  raw_json={"rule_id": "40111", "level": 9, "host": "hr-workstation-02"}),
        ]

        for alert in alerts:
            db.add(alert)
        db.commit()
        print(f"Seeded {len(alerts)} alerts.")

        # --- Sample Cases ---
        now = datetime.now(timezone.utc)
        cases = [
            Case(id="IR-20260623-0001", title="SSH Brute Force on webserver01",
                 severity=SeverityEnum.high, status=StatusEnum.investigating,
                 breach_type=BreachTypeEnum.unauthorized_access,
                 source_ip="203.0.113.42", source_host="webserver01",
                 alert_id="seed-alert-001", assigned_to="manikandan@org.in",
                 data_categories="Credentials", persons_affected=0,
                 ai_summary="Sustained brute force attack from single IP. 500 failed SSH attempts in 2 minutes suggests automated tooling (Hydra or Medusa). No successful login detected.",
                 ai_confidence=91.5, ai_mitre="T1110.001",
                 immediate_action="Block IP 203.0.113.42 at firewall. Review /var/log/auth.log on webserver01.",
                 detected_at=now - timedelta(hours=3)),

            Case(id="IR-20260623-0002", title="Phishing Attack on Finance Team",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.phishing,
                 source_ip="198.51.100.7", source_host="workstation-finance-03",
                 alert_id="seed-alert-002", assigned_to=None,
                 data_categories="Credentials, PII", persons_affected=12,
                 ai_summary="Malicious URL embedded in email attachment. Finance team targeted. Credential harvesting page detected.",
                 ai_confidence=87.0, ai_mitre="T1566.001",
                 immediate_action="Isolate workstation-finance-03. Notify finance team to change passwords immediately.",
                 detected_at=now - timedelta(hours=1)),

            Case(id="IR-20260623-0003", title="Ransomware Detected on fileserver01",
                 severity=SeverityEnum.critical, status=StatusEnum.contained,
                 breach_type=BreachTypeEnum.ransomware,
                 source_ip=None, source_host="fileserver01",
                 alert_id="seed-alert-003", assigned_to="manikandan@org.in",
                 data_categories="PII, Financial, Health", persons_affected=450,
                 ai_summary="Ransomware signatures detected. Files actively being encrypted. Lateral movement risk from fileserver01 to backup systems.",
                 ai_confidence=97.2, ai_mitre="T1486",
                 immediate_action="IMMEDIATELY isolate fileserver01 from network. Do NOT shut down — preserve RAM for forensics. Activate backup restore plan.",
                 detected_at=now - timedelta(hours=6)),

            Case(id="IR-20260623-0004", title="Suspected Data Exfiltration from DB Server",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.exfiltration,
                 source_ip="10.0.0.45", source_host="db-server-01",
                 alert_id="seed-alert-004", assigned_to=None,
                 data_categories="PII, Health", persons_affected=None,
                 ai_summary="Anomalous outbound traffic (4.2GB in 15 minutes) from database server to external IP. Pattern consistent with automated exfiltration tool.",
                 ai_confidence=78.5, ai_mitre="T1041",
                 immediate_action="Capture network traffic dump. Block outbound connections from db-server-01. Audit database access logs.",
                 detected_at=now - timedelta(minutes=45)),

            Case(id="IR-20260623-0005", title="Insider Access Anomaly — HR Workstation",
                 severity=SeverityEnum.medium, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.insider,
                 source_ip="10.0.0.12", source_host="hr-workstation-02",
                 alert_id="seed-alert-005", assigned_to=None,
                 data_categories="PII", persons_affected=None,
                 ai_summary="Privileged account accessed sensitive HR records at 2:30 AM — outside business hours. No scheduled maintenance active. Possible insider threat or compromised credential.",
                 ai_confidence=65.0, ai_mitre="T1078",
                 immediate_action="Review access logs for hr-workstation-02. Suspend privileged account pending investigation. Check if badge access matches digital access.",
                 detected_at=now - timedelta(minutes=20)),
        ]

        for case in cases:
            db.add(case)
        db.commit()
        print(f"Seeded {len(cases)} cases.")
        print("\nSeed complete. Cases created:")
        for c in cases:
            print(f"  {c.id} — {c.title} [{c.severity.value.upper()}] [{c.status.value}]")

    finally:
        db.close()

if __name__ == "__main__":
    seed()
```

Run it:
```bash
cd backend
source venv/bin/activate
python scripts/seed_data.py
```

Expected output:
```
Cleared existing cases and alerts.
Seeded 5 alerts.
Seeded 5 cases.

Seed complete. Cases created:
  IR-20260623-0001 — SSH Brute Force on webserver01 [HIGH] [investigating]
  IR-20260623-0002 — Phishing Attack on Finance Team [HIGH] [open]
  IR-20260623-0003 — Ransomware Detected on fileserver01 [CRITICAL] [contained]
  IR-20260623-0004 — Suspected Data Exfiltration from DB Server [HIGH] [open]
  IR-20260623-0005 — Insider Access Anomaly — HR Workstation [MEDIUM] [open]
```

---

### Task 6.2 — Verify everything in Swagger UI

Open http://localhost:8000/docs

Walk through every endpoint and confirm:
- All endpoints are visible with correct tags (Alerts / Cases / System)
- Each endpoint shows the correct request schema and example
- Each endpoint shows the correct response schema
- Descriptions are readable and useful

Test each endpoint directly from Swagger (click "Try it out"):
- `GET /cases` — should return 5 cases from seed data
- `GET /cases?status=open` — should return 4 cases
- `GET /cases?severity=critical` — should return 1 case (ransomware)
- `GET /cases/IR-20260623-0003` — full ransomware case detail
- `PATCH /cases/IR-20260623-0002` with `{"status": "investigating"}` — should update
- `GET /alerts` — should return 5 alerts
- `POST /alerts` — send a new test alert

---

### Task 6.3 — Verify data integrity in PostgreSQL

```bash
# All 5 cases exist
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, title, severity, status FROM cases ORDER BY detected_at;"

# All 5 alerts exist and are linked to cases
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT a.id, a.level, a.host, c.id as case_id
      FROM alerts a
      LEFT JOIN cases c ON c.alert_id = a.id
      ORDER BY a.received_at;"

# The critical case (ransomware) has correct data
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, severity, persons_affected, data_categories, ai_confidence
      FROM cases WHERE severity = 'critical';"
```

Commit:
```bash
git add backend/scripts/
git commit -m "feat: seed script with 5 sample cases covering all breach types"
```

---

## Day 7 — Final Verification + Week 2 Completion Check

### Task 7.1 — Run the full completion checklist

```bash
# Check 1: All 6 endpoints respond correctly
curl -s http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'; print('✓ Health OK')"
curl -s http://localhost:8000/cases | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d)==5; print('✓ GET /cases returns 5 cases')"
curl -s http://localhost:8000/cases/IR-20260623-0003 | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['severity']=='critical'; print('✓ GET /cases/{id} returns correct case')"
curl -s http://localhost:8000/alerts | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d)==5; print('✓ GET /alerts returns 5 alerts')"

# Check 2: Case ID generation is correct format
curl -s http://localhost:8000/cases | python3 -c "
import sys, json, re
cases = json.load(sys.stdin)
for c in cases:
    assert re.match(r'IR-\d{8}-\d{4}', c['id']), f'Bad ID: {c[\"id\"]}'
print('✓ All case IDs follow IR-YYYYMMDD-XXXX format')
"

# Check 3: Duplicate alert rejection works
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"seed-alert-001","wazuh_rule_id":5710,"level":12,"description":"test","host":"test","raw_json":{}}')
[ "$RESP" = "409" ] && echo "✓ Duplicate alert correctly rejected (409)" || echo "✗ Expected 409, got $RESP"

# Check 4: Filtering works
COUNT=$(curl -s "http://localhost:8000/cases?severity=critical" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "1" ] && echo "✓ Severity filter works" || echo "✗ Expected 1 critical case, got $COUNT"

# Check 5: PATCH update persists
curl -s -X PATCH http://localhost:8000/cases/IR-20260623-0005 \
  -H "Content-Type: application/json" \
  -d '{"status": "investigating", "notes": "Week 2 test"}' > /dev/null
STATUS=$(curl -s http://localhost:8000/cases/IR-20260623-0005 | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[ "$STATUS" = "investigating" ] && echo "✓ PATCH /cases/{id} persists correctly" || echo "✗ Status was $STATUS"

# Check 6: Validation rejects bad input
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"title": "x"}')
[ "$RESP" = "422" ] && echo "✓ Validation correctly rejects incomplete input" || echo "✗ Expected 422, got $RESP"
```

---

### Task 7.2 — Final commit and tag

```bash
git add .
git commit -m "feat: week 2 complete — case manager REST API, alert ingestion, seed data"
git tag v0.2.0-week2
git push origin main --tags
```

---

## Week 2 Summary

| Day | What you built | Verification |
|-----|---------------|-------------|
| 1 | Pydantic schemas for alerts and cases (create, update, list, detail) | Schema validation rejects bad input cleanly |
| 2 | Case service — ID generator, create-from-alert, rule-based classifier | `IR-YYYYMMDD-XXXX` format, correct breach_type mapping |
| 3 | Alerts router — POST /alerts ingests Wazuh alert and creates case | `curl POST /alerts` returns 201 with case detail |
| 4 | Cases router — GET, POST, PATCH, DELETE with filtering and pagination | All endpoints return correct data from Swagger |
| 5 | Global error handlers, field validators (IP, DPDP data categories) | 422 on bad input, 404 on missing resources, 409 on duplicate |
| 6 | Seed script with 5 realistic cases covering all 5 breach types | `python scripts/seed_data.py` populates dev DB |
| 7 | Full checklist — 6 automated checks all pass | All checks green |

**You are now ready for Week 3 — AI Agent Integration (Ollama Classification).**

---

*ZeroRespond · Manikandan · KCT 2023–2027*
