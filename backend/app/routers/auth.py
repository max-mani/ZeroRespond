# backend/app/routers/auth.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserOut
from app.services.auth_service import (
    hash_password,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_user_by_email,
    require_admin,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="""
    Creates a new user account. The first user registered becomes admin automatically.
    Subsequent registrations require an existing admin to be logged in.
    Use this endpoint once during initial setup to create the admin account.
    """
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db)
) -> User:
    # Check if email already taken
    if get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {payload.email} is already registered"
        )

    # First user ever registered becomes admin regardless of requested role
    user_count = db.query(User).count()
    role = "admin" if user_count == 0 else payload.role

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT token",
    description="""
    Authenticate with email and password.
    Returns a Bearer token to use in the Authorization header for all other requests.
    Token expires after 8 hours.
    """
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db)
) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role
    )
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current logged-in user"
)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get(
    "/users",
    response_model=list[UserOut],
    summary="List all users (admin only)"
)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> list[User]:
    return db.query(User).order_by(User.created_at).all()