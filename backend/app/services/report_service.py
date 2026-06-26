# backend/app/services/report_service.py
"""
DPDP Act 2023 breach notification report generator.
Uses WeasyPrint to convert Jinja2 HTML templates to PDF.
All report files are stored in data/reports/.
"""
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.org_profile import OrgProfile

logger = logging.getLogger(__name__)

# Directory where generated PDFs are saved
REPORTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reports"
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def _get_or_create_default_org(db: Session) -> OrgProfile:
    """
    Get the organisation profile, or create a default one if none exists.
    In production, the org profile is set up once via the API.
    """
    org = db.query(OrgProfile).first()
    if not org:
        # Create a default placeholder so reports always work
        org = OrgProfile(
            name="Organisation Name — Update in Settings",
            dpo_name="Data Protection Officer",
            dpo_email="dpo@organisation.in",
            address="Organisation Address",
            cert_in_email="incident@cert-in.org.in",
        )
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def _format_datetime(dt) -> str:
    """Format a datetime object for display in the report."""
    if dt is None:
        return "Not recorded"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d %B %Y, %I:%M %p IST")


def _calculate_response_time(detected_at, resolved_at) -> str:
    """Calculate human-readable response time."""
    if not detected_at or not resolved_at:
        return None
    delta = resolved_at - detected_at
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes} minutes"


def generate_report(db: Session, case_id: str) -> Path:
    """
    Generate a DPDP Act 2023 breach notification PDF for a case.

    Returns the Path to the generated PDF file.
    Raises ValueError if the case does not exist.
    Raises RuntimeError if PDF generation fails.
    """
    # Fetch the case
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case {case_id} not found")

    # Fetch org profile
    org = _get_or_create_default_org(db)

    # Ensure output directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Build template context
    generated_at = datetime.now(timezone.utc)
    context = {
        "case": {
            "id":               case.id,
            "title":            case.title,
            "severity":         case.severity.value,
            "status":           case.status.value,
            "breach_type":      case.breach_type.value,
            "data_categories":  case.data_categories,
            "persons_affected": case.persons_affected,
            "source_host":      case.source_host,
            "source_ip":        case.source_ip,
            "assigned_to":      case.assigned_to,
            "ai_summary":       case.ai_summary,
            "ai_confidence":    case.ai_confidence,
            "ai_mitre":         case.ai_mitre,
            "immediate_action": case.immediate_action,
            "notes":            case.notes,
            "detected_at":      _format_datetime(case.detected_at),
            "breach_est_at":    _format_datetime(case.breach_est_at),
            "resolved_at":      _format_datetime(case.resolved_at),
        },
        "org": {
            "name":          org.name,
            "dpo_name":      org.dpo_name,
            "dpo_email":     org.dpo_email,
            "address":       org.address,
            "cert_in_email": org.cert_in_email,
        },
        "generated_at": _format_datetime(generated_at),
        "response_time": _calculate_response_time(case.detected_at, case.resolved_at),
    }

    # Render HTML template
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("dpdp_report.html")
    html_content = template.render(**context)

    # Generate PDF with WeasyPrint
    output_path = REPORTS_DIR / f"DPDP_Report_{case_id}.pdf"
    try:
        HTML(string=html_content, base_url=str(TEMPLATES_DIR)).write_pdf(str(output_path))
        logger.info(f"Generated DPDP report for case {case_id}: {output_path}")
    except Exception as e:
        logger.error(f"PDF generation failed for case {case_id}: {e}")
        raise RuntimeError(f"PDF generation failed: {str(e)}")

    return output_path