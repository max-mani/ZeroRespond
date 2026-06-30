# backend/app/routers/evidence.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path

from app.database import get_db
from app.schemas.evidence import EvidenceOut
from app.services.evidence_service import (
    save_evidence, list_evidence, get_evidence, delete_evidence
)
from app.services.auth_service import get_current_user, require_admin
from app.models.user import User
from app.models.case import Case
from app.models.evidence import Evidence

# Mounted at /cases/{id}/evidence
cases_evidence_router = APIRouter(prefix="/cases", tags=["Evidence"])

# Mounted at /evidence/{id} for direct download/delete
evidence_router = APIRouter(prefix="/evidence", tags=["Evidence"])


@cases_evidence_router.post(
    "/{case_id}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload evidence file for a case",
    description="""
    Upload a forensic evidence file (screenshot, log export, pcap, etc.) for a case.
    Files are stored under data/evidence/{case_id}/ and tracked in the database.

    Allowed file types: .png, .jpg, .jpeg, .pdf, .txt, .log, .csv, .json, .pcap, .pcapng, .zip, .evtx
    Maximum file size: 50MB
    """
)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Evidence:
    evidence = await save_evidence(
        db=db,
        case_id=case_id,
        file=file,
        description=description,
        uploaded_by=current_user.email
    )
    return evidence


@cases_evidence_router.get(
    "/{case_id}/evidence",
    response_model=List[EvidenceOut],
    summary="List evidence files for a case"
)
def get_case_evidence(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Evidence]:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    return list_evidence(db, case_id)


@evidence_router.get(
    "/{evidence_id}/download",
    summary="Download an evidence file"
)
def download_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    evidence = get_evidence(db, evidence_id)
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence {evidence_id} not found"
        )

    file_path = Path(evidence.filepath)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence file is missing from disk. It may have been moved or deleted manually."
        )

    return FileResponse(
        path=str(file_path),
        filename=evidence.filename,
        media_type="application/octet-stream"
    )


@evidence_router.delete(
    "/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an evidence file (admin only)"
)
def delete_evidence_route(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    deleted = delete_evidence(db, evidence_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence {evidence_id} not found"
        )