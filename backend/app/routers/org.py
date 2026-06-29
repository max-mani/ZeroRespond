# backend/app/routers/org.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.org_profile import OrgProfile
from app.schemas.org import OrgProfileOut, OrgProfileUpdate
from app.services.auth_service import get_current_user, require_admin
from app.models.user import User

router = APIRouter(prefix="/org", tags=["Organisation"])


@router.get(
    "",
    response_model=OrgProfileOut,
    summary="Get organisation profile",
    description="Returns the organisation profile used in DPDP reports. Any authenticated user can read this."
)
def get_org(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> OrgProfile:
    org = db.query(OrgProfile).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation profile not set up yet. Use PUT /org to create it."
        )
    return org


@router.put(
    "",
    response_model=OrgProfileOut,
    summary="Create or update organisation profile (admin only)",
    description="""
    Creates the org profile if it does not exist, or updates it.
    Only admin users can update org settings.
    This data appears in all DPDP breach notification PDFs.
    """
)
def update_org(
    payload: OrgProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)   # admin only
) -> OrgProfile:
    org = db.query(OrgProfile).first()

    if not org:
        # Create new org profile
        org = OrgProfile(
            name=payload.name or "Organisation Name",
            dpo_name=payload.dpo_name or "Data Protection Officer",
            dpo_email=payload.dpo_email or "dpo@organisation.in",
            address=payload.address,
            cert_in_email=payload.cert_in_email or "incident@cert-in.org.in",
        )
        db.add(org)
    else:
        # Update only provided fields
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(org, field, value)

    db.commit()
    db.refresh(org)
    return org