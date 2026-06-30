# backend/app/services/evidence_service.py
"""
Evidence file storage for ZeroRespond.
Files are stored on disk under data/evidence/{case_id}/ and tracked in the DB.
"""
import os
import uuid
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException, status

from app.models.evidence import Evidence
from app.models.case import Case

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "evidence"

# Security limits — tune these for your client's environment
MAX_FILE_SIZE_MB  = 50
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".pdf", ".txt", ".log",
    ".csv", ".json", ".pcap", ".pcapng", ".zip", ".evtx"
}


def _validate_file(file: UploadFile, file_size: int) -> None:
    """Reject files that are too large or have a disallowed extension."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({file_size / 1024 / 1024:.1f}MB). Max allowed: {MAX_FILE_SIZE_MB}MB"
        )


async def save_evidence(
    db: Session,
    case_id: str,
    file: UploadFile,
    description: str | None,
    uploaded_by: str
) -> Evidence:
    """
    Save an uploaded file to disk under data/evidence/{case_id}/
    and create an Evidence DB record.

    Raises HTTPException 404 if case not found, 400 if file is invalid.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )

    content = await file.read()
    file_size = len(content)
    await file.seek(0)

    _validate_file(file, file_size)

    case_dir = EVIDENCE_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = case_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(content)

    evidence = Evidence(
        case_id=case_id,
        filename=file.filename,
        filepath=str(file_path),
        description=description,
        file_size=file_size,
        uploaded_by=uploaded_by,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)

    logger.info(f"Evidence uploaded for case {case_id}: {file.filename} ({file_size} bytes)")
    return evidence


def list_evidence(db: Session, case_id: str) -> list[Evidence]:
    """List all evidence files for a case, newest first."""
    return db.query(Evidence).filter(
        Evidence.case_id == case_id
    ).order_by(Evidence.uploaded_at.desc()).all()


def get_evidence(db: Session, evidence_id: int) -> Evidence | None:
    return db.query(Evidence).filter(Evidence.id == evidence_id).first()


def delete_evidence(db: Session, evidence_id: int) -> bool:
    """
    Delete an evidence record AND its file from disk.
    Returns False if the evidence does not exist.
    """
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        return False

    file_path = Path(evidence.filepath)
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError as e:
            logger.error(f"Failed to delete evidence file {file_path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete evidence file from disk"
            )

    db.delete(evidence)
    db.commit()
    return True