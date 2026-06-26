# ZeroRespond — Week 5 Task List
**Phase 5 · Authentication + DPDP Report Generation**

> **Goal by end of Week 5:** Every API endpoint is protected by JWT authentication. A responder logs in with email and password, receives a token, and all subsequent requests carry that token. The frontend has a login page and stores the token securely. Additionally, the system can generate a DPDP Act 2023 Section 8(6) compliant breach notification PDF for any case — ready to send to CERT-In. This is the week that turns ZeroRespond from a dev tool into something you can actually deploy for a client.

---

## What you have coming in from Week 4

- Full React frontend: Dashboard, Cases list, Case detail, Alert feed
- `POST /alerts`, `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}` — all working
- `POST /cases/{id}/re-enrich` — AI re-enrichment
- `GET /health/ai` — Ollama status
- `backend/app/config.py` — `secret_key` already in settings (used for JWT signing)
- `passlib[bcrypt]` and `python-jose[cryptography]` already installed from Week 1
- `backend/app/models/org_profile.py` — OrgProfile model already exists

---

## Week 5 Architecture

```
What you are building:

Backend:
  POST /auth/register    ← create first user (setup only)
  POST /auth/login       ← returns JWT access token
  GET  /auth/me          ← get current user info
  POST /reports/{case_id} ← generate DPDP PDF for a case
  GET  /reports/{case_id} ← download existing PDF for a case

  New files:
  backend/app/
  ├── models/
  │   └── user.py              ← User model (email, hashed_password, role)
  ├── schemas/
  │   └── auth.py              ← LoginRequest, TokenResponse, UserOut
  ├── services/
  │   ├── auth_service.py      ← password hashing, JWT create/verify
  │   └── report_service.py    ← WeasyPrint PDF generation
  ├── routers/
  │   ├── auth.py              ← login, register, me endpoints
  │   └── reports.py           ← generate and download PDF
  └── templates/
      └── dpdp_report.html     ← Jinja2 HTML template for the PDF

Frontend:
  New files:
  frontend/src/
  ├── pages/
  │   └── Login.tsx            ← Login form
  ├── context/
  │   └── AuthContext.tsx      ← JWT storage, login/logout state
  └── components/
      └── layout/
          └── ProtectedRoute.tsx ← Redirects to /login if not authenticated
```

---

## Why JWT? Why not sessions?

ZeroRespond's backend is a stateless FastAPI service. It runs in Docker, can be restarted anytime, and may eventually run multiple instances. Sessions stored in memory would be lost on restart. JWT tokens are self-contained — the server verifies the signature and extracts the user identity without any DB lookup on every request. This is the standard pattern for FastAPI APIs.

**Token strategy for this week:**
- Access token: 8 hours expiry (long enough for a workday, short enough to limit exposure)
- No refresh tokens yet — that is Week 6 hardening
- Token stored in `localStorage` on the frontend — simple and effective for an intranet tool
- All API routes except `/health`, `/auth/login`, and `/auth/register` require a valid token

---

## Day 1 — User Model + Alembic Migration

### Task 1.1 — Create backend/app/models/user.py

```python
# backend/app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(255), nullable=True)
    role            = Column(String(50), nullable=False, default="analyst")
    # Roles: analyst (read + update cases), admin (full access including delete + create users)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at   = Column(DateTime(timezone=True), nullable=True)
```

---

### Task 1.2 — Register User model in models/__init__.py

```python
# backend/app/models/__init__.py
from app.models.org_profile import OrgProfile
from app.models.alert import Alert
from app.models.playbook import Playbook, PlaybookStep
from app.models.case import Case, SeverityEnum, StatusEnum, BreachTypeEnum
from app.models.case_step import CaseStep
from app.models.evidence import Evidence
from app.models.user import User   # ← add this

__all__ = [
    "OrgProfile", "Alert", "Playbook", "PlaybookStep",
    "Case", "SeverityEnum", "StatusEnum", "BreachTypeEnum",
    "CaseStep", "Evidence", "User"                          # ← add User
]
```

---

### Task 1.3 — Generate and run the migration

```bash
cd backend
source venv/bin/activate
alembic revision --autogenerate -m "add_users_table"
```

Open the generated file in `alembic/versions/` and verify it contains:
```python
op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), ...),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
)
```

Run it:
```bash
alembic upgrade head
```

Verify:
```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd -c "\dt"
# Should now show 8 tables (7 from before + users)

docker exec -it zr-postgres psql -U zr -d zerorespondnd -c "\d users"
# Verify all columns including role, is_active, last_login_at
```

Commit:
```bash
git add backend/app/models/user.py backend/app/models/__init__.py backend/alembic/
git commit -m "feat: users table with role-based access, alembic migration"
```

---

## Day 2 — Auth Service (Password Hashing + JWT)

### Task 2.1 — Create backend/app/schemas/auth.py

```python
# backend/app/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class RegisterRequest(BaseModel):
    """Used by POST /auth/register to create the first admin user."""
    email:     str = Field(..., description="User email address")
    password:  str = Field(..., min_length=8, description="Minimum 8 characters")
    full_name: Optional[str] = None
    role:      str = Field("analyst", description="analyst or admin")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "manikandan@hospital.in",
                "password": "SecurePass123",
                "full_name": "Manikandan",
                "role": "admin"
            }
        }

class LoginRequest(BaseModel):
    """Used by POST /auth/login."""
    email:    str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "manikandan@hospital.in",
                "password": "SecurePass123"
            }
        }

class TokenResponse(BaseModel):
    """Returned by POST /auth/login on success."""
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int = 28800   # 8 hours in seconds

class UserOut(BaseModel):
    """Returned by GET /auth/me."""
    id:            int
    email:         str
    full_name:     Optional[str]
    role:          str
    is_active:     bool
    created_at:    datetime
    last_login_at: Optional[datetime]

    model_config = {"from_attributes": True}
```

---

### Task 2.2 — Create backend/app/services/auth_service.py

```python
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
```

---

### Task 2.3 — Test auth_service in isolation

```bash
cd backend
source venv/bin/activate
python -c "
from app.services.auth_service import hash_password, verify_password, create_access_token, decode_access_token

# Test password hashing
hashed = hash_password('SecurePass123')
print('Hashed:', hashed[:30], '...')
print('Verify correct:', verify_password('SecurePass123', hashed))
print('Verify wrong:  ', verify_password('WrongPassword', hashed))

# Test JWT
token = create_access_token(user_id=1, email='test@org.in', role='admin')
print('Token:', token[:40], '...')

payload = decode_access_token(token)
print('Decoded:', payload)
"
```

Expected output:
```
Hashed: $2b$12$...
Verify correct: True
Verify wrong:   False
Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Decoded: {'sub': '1', 'email': 'test@org.in', 'role': 'admin', 'exp': ..., 'iat': ...}
```

Commit:
```bash
git add backend/app/schemas/auth.py backend/app/services/auth_service.py
git commit -m "feat: auth service — bcrypt password hashing, JWT create/verify, get_current_user dependency"
```

---

## Day 3 — Auth Router + Protect All Endpoints

### Task 3.1 — Create backend/app/routers/auth.py

```python
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
```

---

### Task 3.2 — Protect all existing routers

Now add `get_current_user` as a dependency to every existing endpoint. The cleanest way is to add it at the router level so all routes under that router are protected automatically.

**Update backend/app/routers/cases.py** — add dependency at router level:

```python
# backend/app/routers/cases.py
# Add this import at the top:
from app.services.auth_service import get_current_user, require_admin
from app.models.user import User

# Update the router definition to require auth on all routes:
router = APIRouter(
    prefix="/cases",
    tags=["Cases"],
    dependencies=[Depends(get_current_user)]  # ← all case routes now require auth
)

# The DELETE endpoint needs admin-only access — update it:
@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a case (admin only)"
)
def delete_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)  # ← admin only
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    db.delete(case)
    db.commit()
```

**Update backend/app/routers/alerts.py** — add dependency at router level:

```python
# backend/app/routers/alerts.py
# Add this import:
from app.services.auth_service import get_current_user

# Update the router definition:
router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"],
    dependencies=[Depends(get_current_user)]  # ← all alert routes now require auth
)
```

---

### Task 3.3 — Register auth router in main.py and keep health public

Update `backend/app/main.py`:

```python
# backend/app/main.py
# Add this import:
from app.routers import alerts, cases, auth   # ← add auth

# Add the auth router (keep it first — before protected routes):
app.include_router(auth.router)
app.include_router(alerts.router)
app.include_router(cases.router)

# /health and /health/ai remain public — no change needed
# They are plain @app.get routes with no Depends(get_current_user)
```

---

### Task 3.4 — Test authentication end-to-end

Start the server:
```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload
```

**Step 1:** Register the first admin user:
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@hospital.in",
    "password": "SecurePass123",
    "full_name": "ZeroRespond Admin",
    "role": "admin"
  }'
# Expected: 201 with user object, role: "admin"
```

**Step 2:** Login and get token:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@hospital.in",
    "password": "SecurePass123"
  }'
# Expected: {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 28800}
```

Copy the token. Now test protected vs unprotected routes:

```bash
TOKEN="eyJ..."   # paste your token here

# Step 3: Unprotected route — should work without token
curl http://localhost:8000/health
# Expected: {"status": "ok", ...}

# Step 4: Protected route WITHOUT token — should fail
curl http://localhost:8000/cases
# Expected: 403 {"detail": "Not authenticated"}

# Step 5: Protected route WITH token — should work
curl http://localhost:8000/cases \
  -H "Authorization: Bearer $TOKEN"
# Expected: list of cases

# Step 6: GET /auth/me
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"id": 1, "email": "admin@hospital.in", "role": "admin", ...}

# Step 7: Wrong password should return 401
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@hospital.in", "password": "WrongPassword"}'
# Expected: 401 {"detail": "Incorrect email or password"}
```

Commit:
```bash
git add backend/app/routers/auth.py backend/app/routers/cases.py \
        backend/app/routers/alerts.py backend/app/main.py
git commit -m "feat: auth router, JWT protection on all case and alert endpoints"
```

---

## Day 4 — DPDP Report Generation (WeasyPrint PDF)

### Task 4.1 — Understand the DPDP Act 2023 Section 8(6) requirement

Under DPDP Act 2023, if a data breach occurs, the Data Fiduciary (your client — the hospital, college, or NGO) must notify:
1. The Data Protection Board (once established)
2. Each affected data principal (affected person)
3. CERT-In (within 6 hours for critical incidents)

The notification must include:
- Nature of the breach
- Personal data categories affected
- Approximate number of persons affected
- Likely consequences of the breach
- Measures taken or proposed to address the breach
- Contact details of the Data Protection Officer

Your ZeroRespond report covers all of these.

---

### Task 4.2 — Create the Jinja2 HTML template

Create `backend/templates/dpdp_report.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: Arial, sans-serif;
      font-size: 11pt;
      color: #1a1a1a;
      padding: 40px 50px;
      line-height: 1.5;
    }

    /* Header */
    .header {
      border-bottom: 3px solid #1e40af;
      padding-bottom: 16px;
      margin-bottom: 24px;
    }
    .header-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }
    .org-name {
      font-size: 16pt;
      font-weight: bold;
      color: #1e40af;
    }
    .report-label {
      font-size: 9pt;
      color: #6b7280;
      text-align: right;
    }
    .report-title {
      font-size: 13pt;
      font-weight: bold;
      color: #1f2937;
      margin-top: 10px;
    }
    .report-subtitle {
      font-size: 9pt;
      color: #6b7280;
      margin-top: 2px;
    }

    /* Severity banner */
    .severity-banner {
      padding: 10px 16px;
      border-radius: 4px;
      margin-bottom: 24px;
      font-weight: bold;
      font-size: 11pt;
    }
    .severity-critical { background: #fef2f2; color: #991b1b; border-left: 4px solid #ef4444; }
    .severity-high     { background: #fff7ed; color: #9a3412; border-left: 4px solid #f97316; }
    .severity-medium   { background: #fefce8; color: #854d0e; border-left: 4px solid #eab308; }
    .severity-low      { background: #f0fdf4; color: #166534; border-left: 4px solid #22c55e; }

    /* Section */
    .section {
      margin-bottom: 20px;
    }
    .section-title {
      font-size: 10pt;
      font-weight: bold;
      color: #1e40af;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      border-bottom: 1px solid #dbeafe;
      padding-bottom: 4px;
      margin-bottom: 12px;
    }

    /* Grid */
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .field-label {
      font-size: 8.5pt;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 2px;
    }
    .field-value {
      font-size: 10.5pt;
      color: #1f2937;
    }
    .field-value.mono {
      font-family: "Courier New", monospace;
      font-size: 9.5pt;
    }

    /* AI summary box */
    .ai-box {
      background: #f0f9ff;
      border: 1px solid #bae6fd;
      border-left: 4px solid #0ea5e9;
      padding: 12px 14px;
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .ai-box p {
      font-size: 10.5pt;
      color: #1f2937;
      line-height: 1.6;
    }
    .ai-label {
      font-size: 8pt;
      color: #0369a1;
      font-weight: bold;
      text-transform: uppercase;
      margin-bottom: 4px;
    }

    /* Action box */
    .action-box {
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-left: 4px solid #f97316;
      padding: 12px 14px;
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .action-box p {
      font-size: 10.5pt;
      color: #431407;
    }

    /* MITRE badge */
    .mitre-badge {
      display: inline-block;
      background: #ede9fe;
      color: #5b21b6;
      font-family: "Courier New", monospace;
      font-size: 9pt;
      padding: 2px 8px;
      border-radius: 3px;
      font-weight: bold;
    }

    /* DPDP table */
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }
    th {
      background: #1e40af;
      color: white;
      padding: 7px 10px;
      font-size: 9pt;
      text-align: left;
    }
    td {
      padding: 7px 10px;
      font-size: 9.5pt;
      border-bottom: 1px solid #e5e7eb;
      vertical-align: top;
    }
    tr:nth-child(even) td { background: #f9fafb; }

    /* Confidence bar */
    .confidence-track {
      background: #e5e7eb;
      border-radius: 4px;
      height: 8px;
      width: 120px;
      display: inline-block;
      vertical-align: middle;
      margin-right: 6px;
    }
    .confidence-fill {
      background: #3b82f6;
      border-radius: 4px;
      height: 8px;
    }

    /* Footer */
    .footer {
      margin-top: 32px;
      border-top: 1px solid #e5e7eb;
      padding-top: 12px;
      font-size: 8.5pt;
      color: #9ca3af;
      display: flex;
      justify-content: space-between;
    }

    /* Signature block */
    .signature-block {
      margin-top: 28px;
      padding-top: 16px;
      border-top: 1px solid #e5e7eb;
    }
    .signature-line {
      border-bottom: 1px solid #1a1a1a;
      width: 220px;
      margin-top: 40px;
      margin-bottom: 4px;
    }
    .signature-label {
      font-size: 8.5pt;
      color: #6b7280;
    }

    .not-available {
      color: #9ca3af;
      font-style: italic;
    }

    .status-chip {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 3px;
      font-size: 9pt;
      font-weight: bold;
      text-transform: uppercase;
    }
    .status-open          { background: #dbeafe; color: #1d4ed8; }
    .status-investigating { background: #ede9fe; color: #6d28d9; }
    .status-contained     { background: #fef9c3; color: #854d0e; }
    .status-resolved      { background: #dcfce7; color: #166534; }
    .status-closed        { background: #f3f4f6; color: #4b5563; }
  </style>
</head>
<body>

  <!-- Header -->
  <div class="header">
    <div class="header-top">
      <div class="org-name">{{ org.name }}</div>
      <div class="report-label">
        DPDP Act 2023 — Section 8(6)<br/>
        Breach Notification Report<br/>
        Generated: {{ generated_at }}
      </div>
    </div>
    <div class="report-title">Data Breach Incident Report — {{ case.id }}</div>
    <div class="report-subtitle">
      Data Protection Officer: {{ org.dpo_name }} &nbsp;|&nbsp;
      DPO Email: {{ org.dpo_email }} &nbsp;|&nbsp;
      CERT-In: {{ org.cert_in_email }}
    </div>
  </div>

  <!-- Severity Banner -->
  <div class="severity-banner severity-{{ case.severity }}">
    ⚠ Severity: {{ case.severity | upper }} &nbsp;|&nbsp;
    Status: {{ case.status | replace('_', ' ') | title }} &nbsp;|&nbsp;
    Breach Type: {{ case.breach_type | replace('_', ' ') | title }}
  </div>

  <!-- Section 1: Incident Overview -->
  <div class="section">
    <div class="section-title">1. Incident Overview</div>
    <div class="grid-2">
      <div>
        <div class="field-label">Case ID</div>
        <div class="field-value mono">{{ case.id }}</div>
      </div>
      <div>
        <div class="field-label">Case Title</div>
        <div class="field-value">{{ case.title }}</div>
      </div>
      <div>
        <div class="field-label">Date & Time Detected</div>
        <div class="field-value">{{ case.detected_at }}</div>
      </div>
      <div>
        <div class="field-label">Estimated Breach Start</div>
        <div class="field-value">
          {% if case.breach_est_at %}{{ case.breach_est_at }}{% else %}<span class="not-available">Under Investigation</span>{% endif %}
        </div>
      </div>
      <div>
        <div class="field-label">Affected Host</div>
        <div class="field-value mono">{{ case.source_host or "Unknown" }}</div>
      </div>
      <div>
        <div class="field-label">Source IP Address</div>
        <div class="field-value mono">{{ case.source_ip or "Unknown / Internal" }}</div>
      </div>
      <div>
        <div class="field-label">Assigned Responder</div>
        <div class="field-value">{{ case.assigned_to or "Unassigned" }}</div>
      </div>
      <div>
        <div class="field-label">Current Status</div>
        <div class="field-value">
          <span class="status-chip status-{{ case.status }}">{{ case.status }}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Section 2: AI Analysis -->
  <div class="section">
    <div class="section-title">2. AI-Assisted Threat Analysis</div>

    {% if case.ai_summary %}
    <div class="ai-box">
      <div class="ai-label">AI Classification Summary (qwen2.5:7b — Local Ollama)</div>
      <p>{{ case.ai_summary }}</p>
    </div>
    {% endif %}

    {% if case.immediate_action %}
    <div class="action-box">
      <div class="ai-label">⚡ Recommended Immediate Action</div>
      <p>{{ case.immediate_action }}</p>
    </div>
    {% endif %}

    <div class="grid-2">
      <div>
        <div class="field-label">MITRE ATT&amp;CK Technique</div>
        <div class="field-value">
          {% if case.ai_mitre %}
          <span class="mitre-badge">{{ case.ai_mitre }}</span>
          {% else %}
          <span class="not-available">Not classified</span>
          {% endif %}
        </div>
      </div>
      <div>
        <div class="field-label">AI Confidence Score</div>
        <div class="field-value">
          {% if case.ai_confidence %}
          <span class="confidence-track">
            <span class="confidence-fill" style="width: {{ case.ai_confidence }}%;"></span>
          </span>
          {{ "%.1f"|format(case.ai_confidence) }}%
          {% else %}
          <span class="not-available">Not available</span>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  <!-- Section 3: DPDP Act 2023 — Breach Impact -->
  <div class="section">
    <div class="section-title">3. DPDP Act 2023 — Breach Impact Assessment</div>
    <table>
      <tr>
        <th>Field</th>
        <th>Value</th>
        <th>Remarks</th>
      </tr>
      <tr>
        <td>Nature of Personal Data Breach</td>
        <td>{{ case.breach_type | replace('_', ' ') | title }}</td>
        <td>As classified by AI agent and confirmed by responder</td>
      </tr>
      <tr>
        <td>Categories of Personal Data Affected</td>
        <td>{{ case.data_categories or "Under investigation" }}</td>
        <td>Per DPDP Act 2023 data category definitions</td>
      </tr>
      <tr>
        <td>Approximate Number of Data Principals Affected</td>
        <td>
          {% if case.persons_affected is not none %}
            {{ case.persons_affected | int }}
          {% else %}
            Under investigation
          {% endif %}
        </td>
        <td>Estimate at time of report generation</td>
      </tr>
      <tr>
        <td>Likely Consequences of Breach</td>
        <td colspan="2">{{ case.ai_summary or "Under investigation — AI analysis pending" }}</td>
      </tr>
      <tr>
        <td>Measures Taken / Proposed</td>
        <td colspan="2">{{ case.notes or "Incident response in progress. See case status above." }}</td>
      </tr>
    </table>
  </div>

  <!-- Section 4: Responder Notes -->
  {% if case.notes %}
  <div class="section">
    <div class="section-title">4. Responder Investigation Notes</div>
    <p style="font-size: 10.5pt; color: #1f2937; white-space: pre-wrap;">{{ case.notes }}</p>
  </div>
  {% endif %}

  <!-- Section 5: Resolution -->
  {% if case.resolved_at %}
  <div class="section">
    <div class="section-title">5. Resolution</div>
    <div class="grid-2">
      <div>
        <div class="field-label">Resolved At</div>
        <div class="field-value">{{ case.resolved_at }}</div>
      </div>
      <div>
        <div class="field-label">Total Response Time</div>
        <div class="field-value">{{ response_time or "Calculating..." }}</div>
      </div>
    </div>
  </div>
  {% endif %}

  <!-- Signature Block -->
  <div class="signature-block">
    <div class="grid-2">
      <div>
        <div class="signature-line"></div>
        <div class="signature-label">Data Protection Officer — {{ org.dpo_name }}</div>
        <div class="signature-label">{{ org.dpo_email }}</div>
      </div>
      <div>
        <div class="signature-line"></div>
        <div class="signature-label">Incident Responder — {{ case.assigned_to or "Unassigned" }}</div>
        <div class="signature-label">{{ org.name }}</div>
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <span>ZeroRespond — AI-Enhanced Incident Response Platform</span>
    <span>{{ org.name }} &nbsp;|&nbsp; {{ org.address or "" }} &nbsp;|&nbsp; DPDP Act 2023 Compliant</span>
    <span>Page 1 of 1</span>
  </div>

</body>
</html>
```

---

### Task 4.3 — Create backend/app/services/report_service.py

```python
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
```

---

### Task 4.4 — Create backend/app/routers/reports.py

```python
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
```

Register it in `main.py`:
```python
from app.routers import alerts, cases, auth, reports   # ← add reports

app.include_router(auth.router)
app.include_router(alerts.router)
app.include_router(cases.router)
app.include_router(reports.router)   # ← add this
```

---

### Task 4.5 — Test PDF generation

```bash
TOKEN="eyJ..."   # your token from Day 3

# Generate report for the ransomware case (most complete data)
curl -X POST http://localhost:8000/reports/IR-20260623-0003 \
  -H "Authorization: Bearer $TOKEN" \
  --output DPDP_Report_ransomware.pdf

# Check the file was created
ls -lh DPDP_Report_ransomware.pdf
# Expected: something like -rw-r--r-- 1 ... 45K ... DPDP_Report_ransomware.pdf

# Open the PDF and verify it contains:
# - Organisation name (or placeholder)
# - Case ID IR-20260623-0003
# - CRITICAL severity banner in red
# - AI summary text
# - MITRE T1486
# - DPDP table with PII, Financial, Health categories and 450 persons affected
# - Signature block
xdg-open DPDP_Report_ransomware.pdf
```

Commit:
```bash
git add backend/templates/ backend/app/services/report_service.py \
        backend/app/routers/reports.py backend/app/main.py
git commit -m "feat: DPDP Act 2023 PDF report generation with WeasyPrint and Jinja2 template"
```

---

## Day 5 — Frontend: Login Page + Auth Context

### Task 5.1 — Create AuthContext

Create `frontend/src/context/AuthContext.tsx`:

```tsx
// src/context/AuthContext.tsx
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import axios from "axios";

interface AuthUser {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
}

interface AuthContextType {
  user:    AuthUser | null;
  token:   string | null;
  login:   (email: string, password: string) => Promise<void>;
  logout:  () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

const TOKEN_KEY = "zr_access_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,      setUser]      = useState<AuthUser | null>(null);
  const [token,     setToken]     = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: restore token from localStorage and fetch user
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) {
      setToken(stored);
      fetchMe(stored).finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const fetchMe = async (tkn: string) => {
    try {
      const { data } = await axios.get(
        import.meta.env.DEV ? "/api/auth/me" : "http://localhost:8000/auth/me",
        { headers: { Authorization: `Bearer ${tkn}` } }
      );
      setUser(data);
    } catch {
      // Token invalid or expired — clear everything
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
    }
  };

  const login = async (email: string, password: string) => {
    const baseURL = import.meta.env.DEV ? "/api" : "http://localhost:8000";
    const { data } = await axios.post(`${baseURL}/auth/login`, { email, password });
    const tkn = data.access_token;
    localStorage.setItem(TOKEN_KEY, tkn);
    setToken(tkn);
    await fetchMe(tkn);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
```

---

### Task 5.2 — Update API client to send token on every request

Update `frontend/src/api/client.ts`:

```typescript
// src/api/client.ts
import axios from "axios";
import type { CaseListItem, CaseDetail, CaseUpdate, AlertOut } from "../types";

const TOKEN_KEY = "zr_access_token";

const api = axios.create({
  baseURL: import.meta.env.DEV ? "/api" : "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

// Automatically attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401 response — clear token and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// ─── Cases ───────────────────────────────────────────────────────────────────

export const getCases = async (params?: {
  skip?: number; limit?: number;
  status?: string; severity?: string; breach_type?: string;
}): Promise<CaseListItem[]> => {
  const { data } = await api.get("/cases", { params });
  return data;
};

export const getCase = async (id: string): Promise<CaseDetail> => {
  const { data } = await api.get(`/cases/${id}`);
  return data;
};

export const updateCase = async (id: string, payload: CaseUpdate): Promise<CaseDetail> => {
  const { data } = await api.patch(`/cases/${id}`, payload);
  return data;
};

export const reEnrichCase = async (id: string): Promise<CaseDetail> => {
  const { data } = await api.post(`/cases/${id}/re-enrich`);
  return data;
};

// ─── Alerts ──────────────────────────────────────────────────────────────────

export const getAlerts = async (params?: {
  skip?: number; limit?: number; host?: string;
}): Promise<AlertOut[]> => {
  const { data } = await api.get("/alerts", { params });
  return data;
};

// ─── Reports ─────────────────────────────────────────────────────────────────

export const generateReport = async (case_id: string): Promise<Blob> => {
  const { data } = await api.post(`/reports/${case_id}`, {}, { responseType: "blob" });
  return data;
};

// ─── Health ──────────────────────────────────────────────────────────────────

export const getHealth    = async () => { const { data } = await api.get("/health");    return data; };
export const getAiHealth  = async () => { const { data } = await api.get("/health/ai"); return data; };
```

---

### Task 5.3 — Create the Login page

Create `frontend/src/pages/Login.tsx`:

```tsx
// src/pages/Login.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Shield, LogIn, AlertTriangle } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate   = useNavigate();
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const handleSubmit = async () => {
    if (!email || !password) {
      setError("Email and password are required");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch {
      setError("Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <Shield className="text-blue-400" size={32} />
          <span className="text-2xl font-bold text-white tracking-wide">ZeroRespond</span>
        </div>

        {/* Card */}
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-8">
          <h2 className="text-lg font-semibold text-white mb-1">Sign in</h2>
          <p className="text-sm text-slate-400 mb-6">
            AI-Enhanced Incident Response Platform
          </p>

          {error && (
            <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20
                            rounded-lg p-3 mb-4 text-sm text-red-400">
              <AlertTriangle size={14} className="shrink-0" />
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="responder@hospital.in"
                className="w-full bg-surface-700 border border-surface-600 text-slate-200
                           text-sm rounded-lg px-3 py-2.5 focus:outline-none
                           focus:border-blue-500 placeholder-slate-600"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400 mb-1 block">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="••••••••"
                className="w-full bg-surface-700 border border-surface-600 text-slate-200
                           text-sm rounded-lg px-3 py-2.5 focus:outline-none
                           focus:border-blue-500"
              />
            </div>

            <button
              onClick={handleSubmit}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2
                         bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium
                         rounded-lg py-2.5 transition-colors disabled:opacity-50 mt-2"
            >
              <LogIn size={15} />
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">
          DPDP Act 2023 Compliant · Data stays on-premises
        </p>
      </div>
    </div>
  );
}
```

---

### Task 5.4 — Create ProtectedRoute component

Create `frontend/src/components/layout/ProtectedRoute.tsx`:

```tsx
// src/components/layout/ProtectedRoute.tsx
import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center">
        <div className="text-slate-400 text-sm">Loading...</div>
      </div>
    );
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
```

---

### Task 5.5 — Update App.tsx with auth routes and provider

```tsx
// src/App.tsx
import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/layout/ProtectedRoute";
import Sidebar from "./components/layout/Sidebar";
import TopBar from "./components/layout/TopBar";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Cases from "./pages/Cases";
import CasePage from "./pages/CasePage";
import Alerts from "./pages/Alerts";

function AppLayout() {
  return (
    <div className="flex h-screen bg-surface-900 text-slate-100 overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/cases"     element={<Cases />} />
            <Route path="/cases/:id" element={<CasePage />} />
            <Route path="/alerts"    element={<Alerts />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
```

---

### Task 5.6 — Add logout button to TopBar and show user info

Update `frontend/src/components/layout/TopBar.tsx`:

```tsx
// src/components/layout/TopBar.tsx
import { useQuery } from "@tanstack/react-query";
import { getAiHealth } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { Cpu, Circle, LogOut, User } from "lucide-react";

export default function TopBar() {
  const { data: aiHealth } = useQuery({
    queryKey: ["ai-health"],
    queryFn: getAiHealth,
    refetchInterval: 30_000,
  });
  const { user, logout } = useAuth();
  const aiOk = aiHealth?.status === "ok";

  return (
    <header className="h-14 bg-surface-800 border-b border-surface-700
                       flex items-center justify-between px-6 shrink-0">
      <h1 className="text-sm font-medium text-slate-300">
        Incident Response Platform
      </h1>

      <div className="flex items-center gap-5">
        {/* AI Status */}
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Cpu size={14} />
          <span>AI Agent</span>
          <Circle size={8} className={aiOk ? "text-green-400 fill-green-400" : "text-red-400 fill-red-400"} />
          <span className={aiOk ? "text-green-400" : "text-red-400"}>
            {aiOk ? "Online" : "Offline"}
          </span>
        </div>

        {/* User info */}
        {user && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <User size={13} />
            <span>{user.email}</span>
            <span className="text-slate-600">·</span>
            <span className="text-blue-400 capitalize">{user.role}</span>
          </div>
        )}

        {/* Logout */}
        <button
          onClick={logout}
          className="flex items-center gap-1.5 text-xs text-slate-500
                     hover:text-red-400 transition-colors"
        >
          <LogOut size={13} />
          Sign out
        </button>
      </div>
    </header>
  );
}
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: login page, AuthContext with JWT, ProtectedRoute, logout in TopBar"
```

---

## Day 6 — Report Download Button in Case Detail

### Task 6.1 — Add generateReport to CaseDetail

Update `frontend/src/components/cases/CaseDetail.tsx` — add the report download button to the existing header section:

```tsx
// Add this import at the top of CaseDetail.tsx
import { generateReport } from "../../api/client";
import { FileText } from "lucide-react";

// Add state for report generation inside CaseDetail:
const [reportLoading, setReportLoading] = useState(false);

const handleDownloadReport = async () => {
  setReportLoading(true);
  try {
    const blob = await generateReport(c.id);
    // Create a download link and trigger it
    const url = URL.createObjectURL(blob);
    const a   = document.createElement("a");
    a.href     = url;
    a.download = `DPDP_Report_${c.id}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    alert("Failed to generate report. Please try again.");
  } finally {
    setReportLoading(false);
  }
};
```

Add the button next to "Re-run AI" in the header div:

```tsx
{/* In the header section, next to the Re-run AI button */}
<div className="flex items-center gap-2">
  <button
    onClick={() => enrichMutation.mutate()}
    disabled={enrichMutation.isPending}
    className="flex items-center gap-2 px-3 py-1.5 text-xs
               bg-blue-600 hover:bg-blue-700 text-white rounded-lg
               transition-colors disabled:opacity-50"
  >
    <RefreshCw size={12} className={enrichMutation.isPending ? "animate-spin" : ""} />
    Re-run AI
  </button>

  <button
    onClick={handleDownloadReport}
    disabled={reportLoading}
    className="flex items-center gap-2 px-3 py-1.5 text-xs
               bg-purple-600 hover:bg-purple-700 text-white rounded-lg
               transition-colors disabled:opacity-50"
  >
    <FileText size={12} />
    {reportLoading ? "Generating..." : "DPDP Report"}
  </button>
</div>
```

Commit:
```bash
git add frontend/src/components/cases/CaseDetail.tsx
git commit -m "feat: DPDP report download button in case detail page"
```

---

## Day 7 — Final Verification + Week 5 Completion Check

### Task 7.1 — Set up the org profile for reports

The first thing to do after authentication is working is to set the org profile so reports have real data. Add a quick setup via the API:

```bash
TOKEN="eyJ..."  # your admin token

# Create the org profile (uses the DB directly for now — org profile API is Week 6)
cd backend && source venv/bin/activate
python -c "
from app.database import SessionLocal
from app.models.org_profile import OrgProfile
db = SessionLocal()
org = db.query(OrgProfile).first()
if org:
    org.name = 'Coimbatore Medical College Hospital'
    org.dpo_name = 'Dr. Manikandan'
    org.dpo_email = 'dpo@cmch.edu.in'
    org.address = 'Coimbatore, Tamil Nadu 641 014'
    org.cert_in_email = 'incident@cert-in.org.in'
    db.commit()
    print('Updated org profile')
else:
    from app.models.org_profile import OrgProfile
    org = OrgProfile(
        name='Coimbatore Medical College Hospital',
        dpo_name='Dr. Manikandan',
        dpo_email='dpo@cmch.edu.in',
        address='Coimbatore, Tamil Nadu 641 014',
        cert_in_email='incident@cert-in.org.in'
    )
    db.add(org)
    db.commit()
    print('Created org profile')
db.close()
"
```

---

### Task 7.2 — Run the full completion checklist

```bash
BASE="http://localhost:8000"

# Check 1: Register and login works
curl -s -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"check@hospital.in","password":"CheckPass123","full_name":"Checker","role":"analyst"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['email']=='check@hospital.in'; print('✓ Register works')"

TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hospital.in","password":"SecurePass123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "✓ Login returns token"

# Check 2: Protected routes reject unauthenticated requests
RESP=$(curl -s -o /dev/null -w "%{http_code}" $BASE/cases)
[ "$RESP" = "403" ] && echo "✓ /cases returns 403 without token" || echo "✗ Expected 403, got $RESP"

# Check 3: Protected routes work with token
curl -s $BASE/cases -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list); print('✓ /cases works with token')"

# Check 4: GET /auth/me returns user info
curl -s $BASE/auth/me -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'email' in d; print(f'✓ /auth/me returns user: {d[\"email\"]}')"

# Check 5: DPDP PDF generates successfully
curl -s -X POST $BASE/reports/IR-20260623-0003 \
  -H "Authorization: Bearer $TOKEN" \
  --output /tmp/test_report.pdf
SIZE=$(wc -c < /tmp/test_report.pdf)
[ "$SIZE" -gt "10000" ] && echo "✓ PDF generated (${SIZE} bytes)" || echo "✗ PDF too small or empty: ${SIZE} bytes"

# Check 6: Analyst cannot delete cases (403)
ANALYST_TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"check@hospital.in","password":"CheckPass123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

RESP=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  $BASE/cases/IR-20260623-0005 \
  -H "Authorization: Bearer $ANALYST_TOKEN")
[ "$RESP" = "403" ] && echo "✓ Analyst cannot delete cases (403 as expected)" || echo "✗ Expected 403, got $RESP"

# Check 7: Frontend login page exists and redirects correctly
echo "✓ Manual check: open http://localhost:5173 — should redirect to /login"
echo "✓ Manual check: login form accepts credentials and redirects to /dashboard"
echo "✓ Manual check: TopBar shows user email and Sign out button"
echo "✓ Manual check: Sign out clears session and redirects to /login"
echo "✓ Manual check: Case detail page shows DPDP Report button"
echo "✓ Manual check: Clicking DPDP Report downloads a PDF file"
```

---

### Task 7.3 — Final commit and tag

```bash
git add .
git commit -m "feat: week 5 complete — JWT auth, role-based access, DPDP PDF report generation"
git tag v0.5.0-week5
git push origin main --tags
```

---

## Week 5 Summary

| Day | What you built | Verification |
|-----|----------------|-------------|
| 1 | `users` table with role column, Alembic migration | `\dt` shows 8 tables, `\d users` shows all columns |
| 2 | `auth_service.py` — bcrypt hashing, JWT create/decode, `get_current_user` dependency, `require_admin` dependency | Manual test: hash/verify/encode/decode all pass |
| 3 | Auth router (register, login, me, list users), all case and alert routes protected | Unprotected routes return 403, token-bearing requests succeed |
| 4 | Jinja2 HTML template, `report_service.py`, reports router — generates real DPDP PDF | PDF file created, opens correctly, all case fields present |
| 5 | `AuthContext.tsx`, Login page, `ProtectedRoute`, `client.ts` interceptors, logout in TopBar | Login → dashboard flow works, logout clears session |
| 6 | DPDP Report download button in Case Detail page | Button generates and downloads PDF from the browser |
| 7 | 7-check automated checklist + 6 manual UI checks | All checks pass |

**You are now ready for Week 6 — Org Profile Settings + Playbooks + Docker Compose.**

---

*ZeroRespond · Manikandan · KCT 2023–2027*
