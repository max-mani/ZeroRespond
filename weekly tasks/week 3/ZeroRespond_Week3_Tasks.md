# ZeroRespond — Week 3 Task List
**Phase 3 · AI Agent Integration · Ollama Classification + Async Priority Queue**

> **Goal by end of Week 3:** Every incoming Wazuh alert is classified by the local Ollama AI agent — not the rule-based placeholder from Week 2. The AI agent returns `attack_type`, `severity`, `summary`, `mitre_technique`, `confidence`, and `immediate_action` as structured JSON. High-severity alerts are processed immediately. A fallback ensures the system never fails even if Ollama is unreachable. All enriched fields are stored in the `cases` table and returned from your existing API endpoints with zero schema changes.

---

## What you have coming in from Week 2

- `POST /alerts` — stores raw alert, classifies with `classify_alert_basic()` (rule-based), creates case
- `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}` — fully working
- `backend/app/services/ollama_client.py` — `call_ollama()` and `parse_llm_json()` already written and tested
- `backend/app/models/case.py` — `ai_summary`, `ai_confidence`, `ai_mitre`, `immediate_action` columns already exist
- `backend/app/schemas/case.py` — `CaseDetail` already exposes all AI fields
- Seed data with 5 cases that have AI fields pre-filled (from Week 2)

This week you are replacing `classify_alert_basic()` with a real AI call and wiring in async processing.

---

## Week 3 Architecture

```
Before Week 3:
POST /alerts → classify_alert_basic() → create case (no AI fields)

After Week 3:
POST /alerts → store alert → enqueue(alert)
                                    ↓
                          Priority Queue (asyncio)
                                    ↓
                          AI Agent Worker (background task)
                                    ↓
                          call_ollama() → parse JSON
                                    ↓
                          update case with AI fields
                                    ↓
                          fallback to rule-based if Ollama unreachable

Files to create/modify this week:
backend/app/
├── services/
│   ├── ai_agent.py          ← NEW: prompt builder + Ollama call + JSON parser
│   ├── alert_queue.py       ← NEW: asyncio priority queue + worker
│   └── case_service.py      ← MODIFY: add update_case_ai_fields()
├── routers/
│   └── alerts.py            ← MODIFY: enqueue alert after storing, not block
└── main.py                  ← MODIFY: start queue worker on app startup
```

---

## Why async? Why a queue?

Before you write any code this week, understand this design decision.

**The problem with synchronous AI calls:**
When `POST /alerts` receives a Wazuh alert, if you call Ollama directly in the request handler, the HTTP response is blocked until the LLM finishes. `qwen2.5:7b` takes 5–15 seconds per classification depending on hardware. In a hospital network, Wazuh can fire 50–200 alerts per minute. Synchronous processing means:
- The 50th alert waits 4–10 minutes for a response
- The alert ingestion pipeline becomes the bottleneck
- Wazuh webhook retries pile up, creating duplicates

**The solution — decouple ingestion from enrichment:**
1. `POST /alerts` stores the raw alert, creates a case with rule-based classification (fast, < 50ms), and returns immediately
2. A background worker picks up the alert from the queue and calls Ollama
3. When AI enrichment is done, the case is updated with the AI fields
4. The next `GET /cases/{id}` call returns the enriched case

This is exactly how production incident response systems work.

**Priority tiers:**
- `level >= 12` (high/critical) → priority 1 — processed immediately
- `level >= 8` (medium) → priority 2 — processed within 30 seconds
- `level < 8` (low) → priority 3 — processed within 5 minutes

---

## Day 1 — AI Agent Prompt Engineering

The quality of your AI classifications depends entirely on how well you write your prompts. This day is about getting the prompt right before wiring it into the system.

---

### Task 1.1 — Understand what the AI agent must return

Every call to the AI agent must return a JSON object with exactly these fields:

```json
{
  "attack_type": "unauthorized_access",
  "severity": "high",
  "confidence": 91.5,
  "summary": "Sustained SSH brute force from single IP. 500 failed attempts in 2 minutes suggests automated tooling. No successful login detected.",
  "mitre_technique": "T1110.001",
  "immediate_action": "Block IP 203.0.113.42 at firewall immediately. Review /var/log/auth.log on webserver01 for any successful authentications."
}
```

Field constraints:
- `attack_type` — must be one of: `ransomware`, `phishing`, `unauthorized_access`, `exfiltration`, `insider`
- `severity` — must be one of: `critical`, `high`, `medium`, `low`
- `confidence` — float between 0.0 and 100.0
- `summary` — plain English, 1-3 sentences, no jargon, readable by a non-security person
- `mitre_technique` — MITRE ATT&CK technique ID (e.g. T1486, T1566.001, T1110.001)
- `immediate_action` — one concrete action the responder should take right now

---

### Task 1.2 — Write and test the system prompt manually

Before writing Python, test your prompt directly in the terminal. This is the fastest way to iterate on prompt quality.

```bash
curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "stream": false,
    "messages": [
      {
        "role": "system",
        "content": "You are a cybersecurity incident response AI for Indian organisations. You classify Wazuh SIEM alerts and return structured JSON only. No markdown, no explanation, no preamble. Return only a valid JSON object.\n\nYou must classify every alert into exactly one attack_type from this list:\n- ransomware: file encryption, ransom demand, crypto-locker behaviour\n- phishing: malicious URLs, email-based attacks, credential harvesting\n- unauthorized_access: brute force, failed logins, authentication bypass\n- exfiltration: large data transfers, unusual outbound traffic, data theft\n- insider: privilege misuse, after-hours access, internal policy violations\n\nSeverity must be one of: critical, high, medium, low\nMITRE technique must be a real ATT&CK ID (T followed by digits)\nConfidence is your certainty score from 0 to 100\nSummary must be plain English that a hospital administrator can understand\nImmediate action must be one specific thing the responder should do right now"
      },
      {
        "role": "user",
        "content": "Classify this Wazuh alert:\nRule ID: 5710\nLevel: 12\nDescription: SSH brute force — multiple authentication failures\nSource IP: 203.0.113.42\nHost: webserver01\nGroups: authentication_failed, sshd\n\nReturn JSON with keys: attack_type, severity, confidence, summary, mitre_technique, immediate_action"
      }
    ],
    "options": { "temperature": 0.1, "num_predict": 500 }
  }'
```

Expected `message.content`:
```json
{
  "attack_type": "unauthorized_access",
  "severity": "high",
  "confidence": 92,
  "summary": "Multiple failed SSH login attempts detected from a single external IP address within a short time window, indicating an automated brute force attack targeting webserver01.",
  "mitre_technique": "T1110.001",
  "immediate_action": "Block IP 203.0.113.42 at the firewall immediately and review /var/log/auth.log on webserver01 for any successful logins."
}
```

Test with all 5 breach types before moving to Task 1.3:

```bash
# Test: Ransomware alert
curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "stream": false,
    "messages": [
      {"role": "system", "content": "You are a cybersecurity AI. Return only valid JSON."},
      {"role": "user", "content": "Classify this Wazuh alert:\nRule ID: 92001\nLevel: 15\nDescription: Ransomware signature detected — files being encrypted\nHost: fileserver01\nGroups: ransomware, encrypt\n\nReturn JSON with keys: attack_type, severity, confidence, summary, mitre_technique, immediate_action"}
    ],
    "options": {"temperature": 0.1}
  }'

# Test: Phishing alert
curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "stream": false,
    "messages": [
      {"role": "system", "content": "You are a cybersecurity AI. Return only valid JSON."},
      {"role": "user", "content": "Classify this Wazuh alert:\nRule ID: 87105\nLevel: 14\nDescription: Malicious URL detected in email attachment\nSource IP: 198.51.100.7\nHost: workstation-finance-03\nGroups: phish, malicious_url\n\nReturn JSON with keys: attack_type, severity, confidence, summary, mitre_technique, immediate_action"}
    ],
    "options": {"temperature": 0.1}
  }'
```

Verify each response parses as valid JSON. Note any cases where the model wraps output in markdown backticks — `parse_llm_json()` already handles this.

---

### Task 1.3 — Create backend/app/services/ai_agent.py

```python
# backend/app/services/ai_agent.py
"""
AI agent for ZeroRespond.
Classifies Wazuh alerts using local Ollama (qwen2.5:7b).
No data leaves the client network.
"""
import logging
from app.services.ollama_client import call_ollama, parse_llm_json
from app.models.case import BreachTypeEnum, SeverityEnum

logger = logging.getLogger(__name__)

# ─── System prompt ────────────────────────────────────────────────────────────
# This prompt is the core of the AI agent. Every word matters.
# Keep it concise — longer prompts increase latency and reduce JSON reliability.

SYSTEM_PROMPT = """You are a cybersecurity incident response AI for Indian organisations.
You classify Wazuh SIEM alerts and return structured JSON only.
No markdown, no explanation, no preamble. Return only a valid JSON object.

Classify every alert into exactly one attack_type:
- ransomware: file encryption, ransom demand, crypto-locker behaviour
- phishing: malicious URLs, email-based attacks, credential harvesting
- unauthorized_access: brute force, failed logins, authentication bypass, port scans
- exfiltration: large data transfers, unusual outbound traffic, data staging
- insider: privilege misuse, after-hours access, internal policy violations

Rules:
- severity must be: critical, high, medium, or low
- mitre_technique must be a real MITRE ATT&CK ID (e.g. T1486, T1566.001, T1110.001)
- confidence is your certainty as a number from 0 to 100
- summary must be plain English readable by a hospital administrator (1-3 sentences)
- immediate_action must be one specific, concrete thing the responder should do right now"""

USER_PROMPT_TEMPLATE = """Classify this Wazuh alert:
Rule ID: {rule_id}
Level: {level} (scale 1-15, 15 is most severe)
Description: {description}
Source IP: {source_ip}
Host: {host}
Groups: {groups}

Return JSON with exactly these keys: attack_type, severity, confidence, summary, mitre_technique, immediate_action"""


async def classify_alert_ai(
    wazuh_rule_id: int,
    level: int,
    description: str,
    source_ip: str | None,
    host: str,
    groups: list[str] | None
) -> dict:
    """
    Classify a Wazuh alert using the local Ollama AI agent.

    Returns a dict with keys:
        attack_type, severity, confidence, summary, mitre_technique, immediate_action

    Raises:
        Exception — if Ollama is unreachable or returns unparseable output.
        Callers should catch this and fall back to classify_alert_basic().
    """
    user_message = USER_PROMPT_TEMPLATE.format(
        rule_id=wazuh_rule_id,
        level=level,
        description=description,
        source_ip=source_ip or "Unknown",
        host=host,
        groups=", ".join(groups) if groups else "None"
    )

    raw = await call_ollama(SYSTEM_PROMPT, user_message)
    result = parse_llm_json(raw)

    # Validate and normalise the returned fields
    result = _validate_and_normalise(result)
    return result


def _validate_and_normalise(result: dict) -> dict:
    """
    Validate AI output and normalise to expected types.
    Fixes common model mistakes without re-calling Ollama.
    """
    # Validate attack_type
    valid_attack_types = {e.value for e in BreachTypeEnum}
    if result.get("attack_type") not in valid_attack_types:
        logger.warning(f"AI returned unknown attack_type '{result.get('attack_type')}', defaulting to unauthorized_access")
        result["attack_type"] = "unauthorized_access"

    # Validate severity
    valid_severities = {e.value for e in SeverityEnum}
    if result.get("severity") not in valid_severities:
        logger.warning(f"AI returned unknown severity '{result.get('severity')}', defaulting to medium")
        result["severity"] = "medium"

    # Validate confidence — clamp to 0-100
    try:
        result["confidence"] = float(result.get("confidence", 50.0))
        result["confidence"] = max(0.0, min(100.0, result["confidence"]))
    except (TypeError, ValueError):
        result["confidence"] = 50.0

    # Validate MITRE technique — basic format check
    mitre = result.get("mitre_technique", "")
    if not isinstance(mitre, str) or not mitre.startswith("T"):
        logger.warning(f"AI returned suspicious MITRE technique '{mitre}'")
        result["mitre_technique"] = mitre  # Keep it, just log the warning

    # Ensure summary and immediate_action are strings
    result["summary"] = str(result.get("summary", "AI classification completed."))
    result["immediate_action"] = str(result.get("immediate_action", "Review the alert and take appropriate action."))

    return result
```

---

### Task 1.4 — Test ai_agent.py manually

```bash
cd backend
source venv/bin/activate
python -c "
import asyncio
from app.services.ai_agent import classify_alert_ai

async def test():
    # Test 1: SSH brute force
    result = await classify_alert_ai(
        wazuh_rule_id=5710,
        level=12,
        description='SSH brute force — 500 failed logins in 2 minutes',
        source_ip='203.0.113.42',
        host='webserver01',
        groups=['authentication_failed', 'sshd']
    )
    print('Test 1 — SSH brute force:')
    for k, v in result.items():
        print(f'  {k}: {v}')

    print()

    # Test 2: Ransomware
    result = await classify_alert_ai(
        wazuh_rule_id=92001,
        level=15,
        description='Ransomware signature detected — files being encrypted',
        source_ip=None,
        host='fileserver01',
        groups=['ransomware', 'encrypt']
    )
    print('Test 2 — Ransomware:')
    for k, v in result.items():
        print(f'  {k}: {v}')

asyncio.run(test())
"
```

Expected output for Test 1:
```
Test 1 — SSH brute force:
  attack_type: unauthorized_access
  severity: high
  confidence: 92.0
  summary: Multiple failed SSH login attempts detected from a single external IP ...
  mitre_technique: T1110.001
  immediate_action: Block IP 203.0.113.42 at the firewall immediately ...
```

Expected output for Test 2:
```
Test 2 — Ransomware:
  attack_type: ransomware
  severity: critical
  confidence: 97.0
  summary: Ransomware activity detected on fileserver01 with files actively being encrypted ...
  mitre_technique: T1486
  immediate_action: Immediately isolate fileserver01 from the network ...
```

Commit:
```bash
git add backend/app/services/ai_agent.py
git commit -m "feat: ai agent with Ollama classification, prompt engineering, field validation"
```

---

## Day 2 — Async Priority Queue

### Task 2.1 — Understand asyncio.PriorityQueue

Python's `asyncio.PriorityQueue` is a min-heap. Items with a lower priority number are processed first. You will use:
- Priority `1` → high/critical alerts (level 12+)
- Priority `2` → medium alerts (level 8-11)
- Priority `3` → low alerts (level < 8)

The queue item is a tuple: `(priority, alert_id)`. The worker pulls from the queue in a continuous loop.

---

### Task 2.2 — Create backend/app/services/alert_queue.py

```python
# backend/app/services/alert_queue.py
"""
Async priority queue for AI alert enrichment.
Decouples alert ingestion (fast) from AI classification (slow).

Priority tiers:
  1 → critical/high (level 12+)  — processed immediately
  2 → medium (level 8-11)        — processed within ~30 seconds
  3 → low (level < 8)            — processed when queue is clear

The worker runs as a FastAPI background task started on app startup.
"""
import asyncio
import logging
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.case import Case, BreachTypeEnum, SeverityEnum
from app.services.ai_agent import classify_alert_ai
from app.services.case_service import classify_alert_basic

logger = logging.getLogger(__name__)

# Global priority queue — shared across all requests
_alert_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()


def get_priority(level: int) -> int:
    """Map Wazuh alert level to queue priority (lower = processed sooner)."""
    if level >= 12:
        return 1   # High/Critical — process immediately
    elif level >= 8:
        return 2   # Medium
    else:
        return 3   # Low


async def enqueue_alert(alert_id: str, level: int) -> None:
    """
    Add an alert to the processing queue.
    Called by the alerts router immediately after storing the alert.
    Non-blocking — returns instantly.
    """
    priority = get_priority(level)
    await _alert_queue.put((priority, alert_id))
    logger.info(f"Enqueued alert {alert_id} with priority {priority} (level {level})")


async def _enrich_alert(alert_id: str, db: Session) -> None:
    """
    Core enrichment logic: call AI agent, update case with results.
    Falls back to rule-based classifier if Ollama is unreachable.
    """
    # Fetch the alert from DB
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        logger.warning(f"Alert {alert_id} not found in DB — skipping enrichment")
        return

    # Find the case linked to this alert
    case = db.query(Case).filter(Case.alert_id == alert_id).first()
    if not case:
        logger.warning(f"No case found for alert {alert_id} — skipping enrichment")
        return

    logger.info(f"Starting AI enrichment for alert {alert_id} → case {case.id}")

    try:
        # Call the AI agent
        ai_result = await classify_alert_ai(
            wazuh_rule_id=alert.wazuh_rule_id,
            level=alert.level,
            description=alert.description,
            source_ip=alert.source_ip,
            host=alert.host,
            groups=alert.groups
        )

        # Update the alert's attack_type
        alert.attack_type = ai_result["attack_type"]

        # Update the case with AI enrichment
        case.breach_type = BreachTypeEnum(ai_result["attack_type"])
        case.severity = SeverityEnum(ai_result["severity"])
        case.ai_summary = ai_result["summary"]
        case.ai_confidence = ai_result["confidence"]
        case.ai_mitre = ai_result["mitre_technique"]
        case.immediate_action = ai_result["immediate_action"]

        db.commit()
        logger.info(
            f"AI enrichment complete for case {case.id}: "
            f"{ai_result['attack_type']} / {ai_result['severity']} / "
            f"confidence={ai_result['confidence']:.1f}"
        )

    except Exception as e:
        # Ollama is down, unreachable, or returned bad JSON
        # Fall back to the rule-based classifier from Week 2
        logger.error(f"AI enrichment failed for alert {alert_id}: {e} — using rule-based fallback")

        try:
            breach_type, severity = classify_alert_basic(alert.level, alert.groups)
            case.breach_type = breach_type
            case.severity = severity
            case.ai_summary = f"AI classification unavailable. Rule-based classification applied: {breach_type.value}."
            case.ai_confidence = 0.0   # 0 signals this was not AI-classified
            db.commit()
            logger.info(f"Fallback classification applied to case {case.id}: {breach_type.value} / {severity.value}")
        except Exception as fallback_error:
            logger.error(f"Fallback also failed for alert {alert_id}: {fallback_error}")
            db.rollback()


async def queue_worker() -> None:
    """
    Continuous background worker that processes alerts from the queue.
    Runs forever — started once on FastAPI startup.
    Never crashes — all errors are caught and logged.
    """
    logger.info("Alert queue worker started.")

    while True:
        try:
            # Block until an item is available
            priority, alert_id = await _alert_queue.get()
            logger.info(f"Processing alert {alert_id} from queue (priority {priority})")

            # Each enrichment gets its own DB session
            db = SessionLocal()
            try:
                await _enrich_alert(alert_id, db)
            finally:
                db.close()

            # Mark task as done
            _alert_queue.task_done()

        except asyncio.CancelledError:
            # Graceful shutdown when FastAPI stops
            logger.info("Queue worker received cancel signal — shutting down.")
            break
        except Exception as e:
            # Unexpected error — log and continue, never crash the worker
            logger.error(f"Unexpected error in queue worker: {e}")
            await asyncio.sleep(1)   # Brief pause before retrying
```

---

### Task 2.3 — Start the worker on FastAPI startup

Update `backend/app/main.py` to start the queue worker as a background task:

```python
# backend/app/main.py
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from app.routers import alerts, cases
from app.services.alert_queue import queue_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

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

# ─── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    return JSONResponse(status_code=422, content={"error": "Validation failed", "detail": errors})

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"error": "Database constraint violation", "detail": str(exc.orig)})

# ─── Lifespan: start queue worker on boot ────────────────────────────────────

_worker_task = None

@app.on_event("startup")
async def startup_event():
    global _worker_task
    _worker_task = asyncio.create_task(queue_worker())
    logger.info("ZeroRespond API started — queue worker running.")

@app.on_event("shutdown")
async def shutdown_event():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    logger.info("ZeroRespond API shutting down — queue worker stopped.")

# ─── Routers ─────────────────────────────────────────────────────────────────

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

---

## Day 3 — Update Alerts Router to Use Queue

### Task 3.1 — Modify backend/app/routers/alerts.py

The alerts router now does three things in sequence:
1. Stores the raw alert (same as before)
2. Creates the case with rule-based classification (same as before — fast fallback)
3. **Enqueues the alert for async AI enrichment (new)**

The route returns the case immediately — the AI enrichment happens in the background.

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
from app.services.alert_queue import enqueue_alert

router = APIRouter(prefix="/alerts", tags=["Alerts"])


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
```

> **Note:** `ingest_alert` is now `async def` (was `def` in Week 2). This is required because it calls `await enqueue_alert(...)`. If you leave it as `def`, FastAPI will run it in a thread pool and `await` will not work.

---

### Task 3.2 — Add update_case_ai_fields to case_service.py

Add this function to `backend/app/services/case_service.py`:

```python
# Add to backend/app/services/case_service.py

def update_case_ai_fields(
    db: Session,
    case_id: str,
    ai_summary: str,
    ai_confidence: float,
    ai_mitre: str,
    immediate_action: str,
    breach_type: BreachTypeEnum,
    severity: SeverityEnum,
) -> Case | None:
    """
    Update a case with AI enrichment results.
    Called by the queue worker after Ollama classification completes.
    Returns None if case not found.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return None

    case.ai_summary      = ai_summary
    case.ai_confidence   = ai_confidence
    case.ai_mitre        = ai_mitre
    case.immediate_action = immediate_action
    case.breach_type     = breach_type
    case.severity        = severity

    db.commit()
    db.refresh(case)
    return case
```

Commit:
```bash
git add backend/app/services/ backend/app/routers/alerts.py backend/app/main.py
git commit -m "feat: async priority queue, AI agent wired into alert ingestion pipeline"
```

---

## Day 4 — End-to-End Testing

### Task 4.1 — Start the full stack

```bash
# Terminal 1: PostgreSQL
docker ps | grep zr-postgres
# If not running:
docker start zr-postgres

# Terminal 2: Ollama (verify it's running)
ollama list
# Should show qwen2.5:7b

# Terminal 3: FastAPI with logging
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --log-level info
```

You should see in Terminal 3:
```
INFO  uvicorn.error: Application startup complete.
INFO  app.services.alert_queue: Alert queue worker started.
INFO  ZeroRespond API started — queue worker running.
```

---

### Task 4.2 — Send a test alert and observe enrichment

**Step 1:** Send the alert:
```bash
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "id": "week3-test-001",
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
      "host": "webserver01"
    }
  }'
```

Expected response (immediate, < 100ms — no AI fields yet):
```json
{
  "id": "IR-20260624-0001",
  "title": "Unauthorized Access on webserver01",
  "severity": "high",
  "status": "open",
  "breach_type": "unauthorized_access",
  "ai_summary": null,
  "ai_confidence": null,
  "ai_mitre": null,
  "immediate_action": null,
  ...
}
```

**Step 2:** Watch the logs in Terminal 3. You should see within a few seconds:
```
INFO  app.services.alert_queue: Enqueued alert week3-test-001 with priority 1 (level 12)
INFO  app.services.alert_queue: Processing alert week3-test-001 from queue (priority 1)
INFO  app.services.alert_queue: Starting AI enrichment for alert week3-test-001 → case IR-20260624-0001
INFO  app.services.alert_queue: AI enrichment complete for case IR-20260624-0001: unauthorized_access / high / confidence=92.0
```

**Step 3:** After the logs confirm enrichment, fetch the case:
```bash
curl http://localhost:8000/cases/IR-20260624-0001
```

Expected response (now enriched):
```json
{
  "id": "IR-20260624-0001",
  "severity": "high",
  "breach_type": "unauthorized_access",
  "ai_summary": "Multiple failed SSH login attempts detected from a single external IP address...",
  "ai_confidence": 92.0,
  "ai_mitre": "T1110.001",
  "immediate_action": "Block IP 203.0.113.42 at the firewall immediately...",
  ...
}
```

---

### Task 4.3 — Test priority ordering

Send three alerts at the same time — one from each priority tier:

```bash
# Low priority (level 5) — should be processed last
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"priority-test-low","wazuh_rule_id":1001,"level":5,"description":"Info: user login","source_ip":null,"host":"workstation-01","groups":["authentication_success"],"raw_json":{}}'

# Medium priority (level 9) — should be processed second
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"priority-test-med","wazuh_rule_id":2001,"level":9,"description":"Privileged access outside hours","source_ip":"10.0.0.12","host":"hr-workstation","groups":["insider","privilege"],"raw_json":{}}'

# High priority (level 14) — should be processed first
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"priority-test-high","wazuh_rule_id":3001,"level":14,"description":"Ransomware detected","source_ip":null,"host":"fileserver01","groups":["ransomware","encrypt"],"raw_json":{}}'
```

Check the logs — you should see the high priority alert processed before the medium, and medium before low.

---

### Task 4.4 — Test Ollama fallback

This test simulates what happens when the AI is unavailable.

**Step 1:** Stop Ollama:
```bash
sudo systemctl stop ollama
```

**Step 2:** Send an alert:
```bash
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"fallback-test-001","wazuh_rule_id":5710,"level":12,"description":"SSH brute force","source_ip":"10.0.0.1","host":"server01","groups":["sshd","authentication_failed"],"raw_json":{}}'
```

**Step 3:** Watch the logs. You should see:
```
ERROR app.services.alert_queue: AI enrichment failed for alert fallback-test-001: ... — using rule-based fallback
INFO  app.services.alert_queue: Fallback classification applied to case IR-...: unauthorized_access / high
```

**Step 4:** Fetch the case and verify it has `ai_confidence: 0.0` and the fallback summary:
```bash
curl http://localhost:8000/cases/<case-id-from-step-2>
```

Expected:
```json
{
  "ai_summary": "AI classification unavailable. Rule-based classification applied: unauthorized_access.",
  "ai_confidence": 0.0,
  "ai_mitre": null,
  "immediate_action": null,
  ...
}
```

**Step 5:** Restart Ollama:
```bash
sudo systemctl start ollama
```

---

## Day 5 — Add AI Status Endpoint + Ollama Health Check

### Task 5.1 — Add Ollama health check to ai_agent.py

```python
# Add to backend/app/services/ai_agent.py

import httpx
from app.config import settings

async def check_ollama_health() -> dict:
    """
    Check if Ollama is running and the required model is available.
    Returns a status dict for the /health/ai endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]

            required_model = settings.ollama_model
            model_available = any(
                m == required_model or m.startswith(required_model.split(":")[0])
                for m in model_names
            )

            return {
                "ollama_running": True,
                "model_available": model_available,
                "model": required_model,
                "available_models": model_names,
                "status": "ready" if model_available else "model_not_found"
            }
    except Exception as e:
        return {
            "ollama_running": False,
            "model_available": False,
            "model": settings.ollama_model,
            "available_models": [],
            "status": "unreachable",
            "error": str(e)
        }
```

---

### Task 5.2 — Add /health/ai endpoint to main.py

```python
# Add to backend/app/main.py

from app.services.ai_agent import check_ollama_health

@app.get("/health/ai", tags=["System"])
async def ai_health_check():
    """
    Check AI agent status — Ollama running, model available, queue depth.
    Use this to verify the AI enrichment pipeline is healthy.
    """
    ai_status = await check_ollama_health()
    return {
        "status": "ok" if ai_status["status"] == "ready" else "degraded",
        "ai_agent": ai_status,
        "fallback": "rule-based classifier active when AI unavailable"
    }
```

Test it:
```bash
# With Ollama running
curl http://localhost:8000/health/ai
# Expected:
# {
#   "status": "ok",
#   "ai_agent": {
#     "ollama_running": true,
#     "model_available": true,
#     "model": "qwen2.5:7b",
#     "status": "ready"
#   },
#   "fallback": "rule-based classifier active when AI unavailable"
# }

# With Ollama stopped
sudo systemctl stop ollama
curl http://localhost:8000/health/ai
# Expected: {"status": "degraded", "ai_agent": {"ollama_running": false, ...}}
sudo systemctl start ollama
```

Commit:
```bash
git add backend/app/services/ai_agent.py backend/app/main.py
git commit -m "feat: Ollama health check endpoint, AI status at /health/ai"
```

---

## Day 6 — Re-enrich Existing Cases + Seed Script Update

### Task 6.1 — Add a re-enrichment endpoint

Sometimes you will want to re-run AI enrichment on an existing case — for example after updating the prompt or switching models.

```python
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
```

---

### Task 6.2 — Update seed script to clear AI fields so you can test enrichment

Update `backend/scripts/seed_data.py` to add a `--no-ai` flag that seeds cases without AI fields, so you can test the enrichment pipeline end-to-end:

```python
# Add to the bottom of backend/scripts/seed_data.py

def seed_without_ai():
    """
    Seed cases WITHOUT AI fields so you can test the enrichment pipeline.
    Usage: python scripts/seed_data.py --no-ai
    """
    db = SessionLocal()
    try:
        db.query(Case).delete()
        db.query(Alert).delete()
        db.commit()

        # Same alerts as the main seed function
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
                  raw_json={"rule_id": "87105", "level": 14}),
            Alert(id="seed-alert-003", wazuh_rule_id=92001, level=15,
                  description="Ransomware signature detected — files being encrypted",
                  source_ip=None, host="fileserver01",
                  groups=["ransomware", "encrypt"],
                  raw_json={"rule_id": "92001", "level": 15}),
            Alert(id="seed-alert-004", wazuh_rule_id=61002, level=10,
                  description="Large outbound data transfer detected",
                  source_ip="10.0.0.45", host="db-server-01",
                  groups=["exfil", "data_leak"],
                  raw_json={"rule_id": "61002", "level": 10}),
            Alert(id="seed-alert-005", wazuh_rule_id=40111, level=9,
                  description="Privileged account access outside business hours",
                  source_ip="10.0.0.12", host="hr-workstation-02",
                  groups=["insider", "privilege"],
                  raw_json={"rule_id": "40111", "level": 9}),
        ]
        for alert in alerts:
            db.add(alert)
        db.commit()

        # Cases WITHOUT AI fields
        now = datetime.now(timezone.utc)
        cases = [
            Case(id="IR-20260623-0001", title="SSH Brute Force on webserver01",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.unauthorized_access,
                 source_ip="203.0.113.42", source_host="webserver01",
                 alert_id="seed-alert-001",
                 detected_at=now - timedelta(hours=3)),
            Case(id="IR-20260623-0002", title="Phishing Attack on Finance Team",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.phishing,
                 source_ip="198.51.100.7", source_host="workstation-finance-03",
                 alert_id="seed-alert-002",
                 detected_at=now - timedelta(hours=1)),
            Case(id="IR-20260623-0003", title="Ransomware Detected on fileserver01",
                 severity=SeverityEnum.critical, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.ransomware,
                 source_ip=None, source_host="fileserver01",
                 alert_id="seed-alert-003",
                 detected_at=now - timedelta(hours=6)),
            Case(id="IR-20260623-0004", title="Suspected Data Exfiltration from DB Server",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.exfiltration,
                 source_ip="10.0.0.45", source_host="db-server-01",
                 alert_id="seed-alert-004",
                 detected_at=now - timedelta(minutes=45)),
            Case(id="IR-20260623-0005", title="Insider Access Anomaly — HR Workstation",
                 severity=SeverityEnum.medium, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.insider,
                 source_ip="10.0.0.12", source_host="hr-workstation-02",
                 alert_id="seed-alert-005",
                 detected_at=now - timedelta(minutes=20)),
        ]
        for case in cases:
            db.add(case)
        db.commit()
        print("Seeded 5 cases WITHOUT AI fields.")
        print("Now call POST /cases/{id}/re-enrich on each case to trigger AI enrichment.")
        for c in cases:
            print(f"  curl -X POST http://localhost:8000/cases/{c.id}/re-enrich")
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    if "--no-ai" in sys.argv:
        seed_without_ai()
    else:
        seed()
```

Run it to test the full enrichment pipeline:
```bash
cd backend
python scripts/seed_data.py --no-ai

# Then re-enrich each case
curl -X POST http://localhost:8000/cases/IR-20260623-0003/re-enrich   # Ransomware — highest priority
curl -X POST http://localhost:8000/cases/IR-20260623-0001/re-enrich
curl -X POST http://localhost:8000/cases/IR-20260623-0002/re-enrich
curl -X POST http://localhost:8000/cases/IR-20260623-0004/re-enrich
curl -X POST http://localhost:8000/cases/IR-20260623-0005/re-enrich

# Wait 30-60 seconds for all to process, then check
curl http://localhost:8000/cases/IR-20260623-0003
# Should show ai_summary, ai_mitre, ai_confidence, immediate_action all filled
```

Commit:
```bash
git add backend/scripts/ backend/app/routers/cases.py
git commit -m "feat: re-enrich endpoint, seed_without_ai mode for pipeline testing"
```

---

## Day 7 — Final Verification + Week 3 Completion Check

### Task 7.1 — Run the full completion checklist

```bash
# Check 1: AI health endpoint shows Ollama is ready
curl -s http://localhost:8000/health/ai | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'ok', f'AI status is not ok: {d}'
assert d['ai_agent']['ollama_running'] == True
assert d['ai_agent']['model_available'] == True
print('✓ Ollama is running and model is available')
"

# Check 2: New alert gets AI fields populated within 30 seconds
curl -s -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"check-week3-001","wazuh_rule_id":92001,"level":15,"description":"Ransomware signature detected","source_ip":null,"host":"fileserver02","groups":["ransomware","encrypt"],"raw_json":{}}' \
  > /tmp/case_response.json

CASE_ID=$(python3 -c "import json; print(json.load(open('/tmp/case_response.json'))['id'])")
echo "Case created: $CASE_ID"

# Wait for AI enrichment
echo "Waiting 30 seconds for AI enrichment..."
sleep 30

curl -s http://localhost:8000/cases/$CASE_ID | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['ai_summary'] is not None, 'ai_summary is null — enrichment did not run'
assert d['ai_confidence'] is not None and d['ai_confidence'] > 0, 'ai_confidence is 0 or null'
assert d['ai_mitre'] is not None, 'ai_mitre is null'
assert d['immediate_action'] is not None, 'immediate_action is null'
print(f'✓ AI enrichment complete: {d[\"attack_type\"]} / {d[\"severity\"]} / confidence={d[\"ai_confidence\"]}')
print(f'  MITRE: {d[\"ai_mitre\"]}')
print(f'  Summary: {d[\"ai_summary\"][:80]}...')
"

# Check 3: High priority alerts processed before low priority
# (Check logs manually — level 12+ should appear in logs before level 5)
echo "✓ Check server logs to confirm priority ordering (high before low)"

# Check 4: Fallback works when Ollama is stopped
sudo systemctl stop ollama
curl -s -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{"id":"check-fallback-001","wazuh_rule_id":5710,"level":12,"description":"Fallback test","source_ip":"1.2.3.4","host":"server-x","groups":["sshd"],"raw_json":{}}' \
  > /tmp/fallback_case.json

FALLBACK_ID=$(python3 -c "import json; print(json.load(open('/tmp/fallback_case.json'))['id'])")
sleep 5

curl -s http://localhost:8000/cases/$FALLBACK_ID | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['ai_confidence'] == 0.0, 'Expected confidence 0.0 for fallback'
assert 'unavailable' in (d.get('ai_summary') or '').lower(), 'Expected fallback message in ai_summary'
print('✓ Fallback classifier works correctly when Ollama is unreachable')
"
sudo systemctl start ollama

# Check 5: Re-enrich endpoint works
curl -s -X POST http://localhost:8000/cases/$CASE_ID/re-enrich | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['id'] is not None
print(f'✓ Re-enrich endpoint works for case {d[\"id\"]}')
"

# Check 6: /health/ai shows degraded when Ollama is down
sudo systemctl stop ollama
sleep 2
curl -s http://localhost:8000/health/ai | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'degraded'
print('✓ /health/ai correctly shows degraded when Ollama is stopped')
"
sudo systemctl start ollama
```

---

### Task 7.2 — Verify AI fields in PostgreSQL

```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, breach_type, severity, ai_confidence, ai_mitre,
             LEFT(ai_summary, 60) as summary_preview,
             LEFT(immediate_action, 60) as action_preview
      FROM cases
      ORDER BY detected_at DESC
      LIMIT 5;"
```

All 5 cases should have non-null `ai_confidence`, `ai_mitre`, and `ai_summary`.

---

### Task 7.3 — Final commit and tag

```bash
git add .
git commit -m "feat: week 3 complete — Ollama AI agent, async priority queue, fallback classifier"
git tag v0.3.0-week3
git push origin main --tags
```

---

## Week 3 Summary

| Day | What you built | Verification |
|-----|----------------|-------------|
| 1 | `ai_agent.py` — system prompt, user prompt template, field validation, normalisation | Manual test: 5 breach types classified correctly |
| 2 | `alert_queue.py` — asyncio priority queue, background worker, fallback to rule-based | Worker starts on FastAPI boot, logs show priority ordering |
| 3 | Updated alerts router — async `ingest_alert`, enqueue after case creation | `POST /alerts` returns in < 100ms, case enriched within 30s |
| 4 | End-to-end testing — enrichment, priority ordering, Ollama fallback | All 4 scenarios pass: enrich, priority, fallback, re-enrich |
| 5 | `/health/ai` endpoint, Ollama health check | Returns `ok` when ready, `degraded` when Ollama is down |
| 6 | Re-enrich endpoint, `--no-ai` seed mode for pipeline testing | `POST /cases/{id}/re-enrich` triggers fresh AI classification |
| 7 | 6-check completion checklist, DB verification | All AI fields populated in PostgreSQL |

**You are now ready for Week 4 — React Frontend (ZeroDashboard).**

---

*ZeroRespond · Manikandan · KCT 2023–2027*
