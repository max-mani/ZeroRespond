# backend/app/routers/reports.py
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.report_service import generate_report, REPORTS_DIR
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post(
    "/{case_id}",
    summary="Generate DPDP breach notification PDF",
    description="""
    Generates a DPDP Act 2023 Section 8(6) compliant breach notification PDF
    for the specified case. The PDF is saved to data/reports/ and returned
    as a downloadable file.

    The report includes:
    - Incident overview (case ID, severity, dates, affected host)
    - AI-assisted threat analysis with MITRE ATT&CK technique
    - DPDP Act 2023 breach impact assessment table
    - Responder notes and resolution details
    - Signature block for DPO and incident responder
    """
)
def generate_case_report(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        output_path = generate_report(db, case_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return FileResponse(
        path=str(output_path),
        media_type="application/pdf",
        filename=f"DPDP_Report_{case_id}.pdf",
        headers={"Content-Disposition": f'attachment; filename="DPDP_Report_{case_id}.pdf"'}
    )


@router.get(
    "/{case_id}",
    summary="Download existing DPDP report PDF",
    description="Download a previously generated PDF. Returns 404 if no report exists yet — call POST first."
)
def download_case_report(
    case_id: str,
    current_user: User = Depends(get_current_user)
):
    output_path = REPORTS_DIR / f"DPDP_Report_{case_id}.pdf"
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No report found for case {case_id}. Call POST /reports/{case_id} to generate one."
        )
    return FileResponse(
        path=str(output_path),
        media_type="application/pdf",
        filename=f"DPDP_Report_{case_id}.pdf"
    )