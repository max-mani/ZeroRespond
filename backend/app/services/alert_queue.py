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