# backend/app/services/auth_service.py
"""
Authentication service for ZeroRespond.
Handles password hashing and JWT creation/verification.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import get_db
from app.models.user import User

# ─── Password hashing ─────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain_password: str) -> str:
    """Hash a plain text password using bcrypt."""
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)

# ─── JWT ──────────────────────────────────────────────────────────────────────

ALGORITHM    = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

def create_access_token(user_id: int, email: str, role: str) -> str:
    """
    Create a signed JWT access token.
    Payload contains user_id, email, role, and expiry time.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub":   str(user_id),   # subject — always a string
        "email": email,
        "role":  role,
        "exp":   expire,
        "iat":   datetime.now(timezone.utc),  # issued at
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Raises HTTPException 401 if invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token — missing subject"
            )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ─── User lookup ──────────────────────────────────────────────────────────────

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Verify email + password. Returns the User if valid, None if not.
    Always runs verify_password even if user not found
    to prevent timing attacks.
    """
    user = get_user_by_email(db, email)
    if not user:
        # Still hash to prevent timing-based user enumeration
        pwd_context.dummy_verify()
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user

# ─── FastAPI dependency: get current user from Bearer token ───────────────────

bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency.
    Extracts Bearer token from Authorization header,
    verifies it, and returns the current User from the DB.

    Usage:
        @router.get("/protected")
        def my_route(current_user: User = Depends(get_current_user)):
            ...
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = int(payload["sub"])

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated"
        )
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency.
    Allows only admin users. Use on destructive or sensitive routes.

    Usage:
        @router.delete("/cases/{id}")
        def delete_case(current_user: User = Depends(require_admin)):
            ...
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this action"
        )
    return current_user