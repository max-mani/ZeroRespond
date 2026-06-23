# ZeroRespond — Week 1 Task List

**Phase 1 · Foundation · Database Schema + FastAPI Project Setup**

> **Goal by end of Week 1:** PostgreSQL running in Docker with all 7 tables created via Alembic migration. FastAPI project boots without errors. You have a clean, professional project structure you will build on for the next 11 weeks. No endpoint logic this week — just setup and schema.

---

## Day 1 — Project Structure + Git + Python Environment

### Task 1.1 — Create the project root and folder structure

```bash
mkdir zerorespondnd && cd zerorespondnd
mkdir -p backend/app/models
mkdir -p backend/app/routers
mkdir -p backend/app/services
mkdir -p backend/app/schemas
mkdir -p backend/alembic
mkdir -p backend/templates
mkdir -p alert-processor
mkdir -p frontend
mkdir -p data/evidence
mkdir -p data/reports
mkdir -p landing
```

Verify the structure looks like this:

```
zerorespondnd/
├── backend/
│   ├── app/
│   │   ├── models/
│   │   ├── routers/
│   │   ├── services/
│   │   └── schemas/
│   ├── alembic/
│   └── templates/
├── alert-processor/
├── frontend/
├── data/
│   ├── evidence/
│   └── reports/
└── landing/
```

---

### Task 1.2 — Initialize Git repository

```bash
cd zerorespondnd
git init
git branch -M main
```

Create `.gitignore` at the project root:

```
# Python
__pycache__/
*.py[cod]
*.pyo
.env
venv/
.venv/
*.egg-info/

# Node
node_modules/
dist/
.next/

# Docker
*.log

# Data (never commit patient/evidence data)
data/evidence/*
data/reports/*
!data/evidence/.gitkeep
!data/reports/.gitkeep

# IDE
.vscode/
.idea/
*.DS_Store
```

Create placeholder files so empty folders are tracked:

```bash
touch data/evidence/.gitkeep
touch data/reports/.gitkeep
```

Initial commit:

```bash
git add .
git commit -m "chore: initial project structure"
```

---

### Task 1.3 — Create Python virtual environment for backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# OR
venv\Scripts\activate      # Windows
```

Verify Python version is 3.11+:

```bash
python --version
# Should output: Python 3.11.x
```

---

### Task 1.4 — Install all backend dependencies

```bash
pip install fastapi uvicorn[standard] sqlalchemy alembic psycopg2-binary \
            pydantic pydantic-settings python-multipart httpx \
            python-jose[cryptography] passlib[bcrypt] \
            jinja2 weasyprint pytest pytest-asyncio httpx
```

Pin all versions by generating requirements.txt immediately:

```bash
pip freeze > requirements.txt
```

Verify key packages installed correctly:

```bash
python -c "import fastapi; print('FastAPI:', fastapi.__version__)"
python -c "import sqlalchemy; print('SQLAlchemy:', sqlalchemy.__version__)"
python -c "import alembic; print('Alembic:', alembic.__version__)"
```

---

### Task 1.5 — Create the .env file and .env.example

Create `backend/.env` (never commit this):

```env
# Database
DATABASE_URL=postgresql://zr:secret@localhost:5432/zerorespondnd

# Ollama (local AI)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Wazuh
WAZUH_URL=https://localhost:55000
WAZUH_USER=wazuh-wui
WAZUH_PASS=changeme

# App
SECRET_KEY=change-this-to-a-random-64-char-string
ENVIRONMENT=development
```

Create `backend/.env.example` (commit this):

```env
# Database
DATABASE_URL=postgresql://zr:secret@localhost:5432/zerorespondnd

# Ollama (local AI — install from https://ollama.ai)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Wazuh SIEM
WAZUH_URL=https://your-wazuh-server:55000
WAZUH_USER=wazuh-wui
WAZUH_PASS=your-wazuh-password

# App Security
SECRET_KEY=generate-with-openssl-rand-hex-32
ENVIRONMENT=development
```

Add `.env` to `.gitignore` (already done in Task 1.2). Commit `.env.example`:

```bash
git add backend/.env.example
git commit -m "chore: add .env.example with all required variables"
```

---

## Day 2 — PostgreSQL + Docker Setup

### Task 2.1 — Install Docker if not already installed

```bash
# Ubuntu 22.04
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
newgrp docker
```

Verify Docker works:

```bash
docker --version
docker compose version
```

---

### Task 2.2 — Run PostgreSQL in Docker

```bash
docker run -d \
  --name zr-postgres \
  -e POSTGRES_DB=zerorespondnd \
  -e POSTGRES_USER=zr \
  -e POSTGRES_PASSWORD=secret \
  -p 5432:5432 \
  -v zr_pgdata:/var/lib/postgresql/data \
  postgres:15-alpine
```

Verify it is running:

```bash
docker ps
# Should show zr-postgres as running

docker logs zr-postgres
# Should end with: "database system is ready to accept connections"
```

Test connection:

```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd -c "\conninfo"
# Should output: You are connected to database "zerorespondnd" as user "zr"
```

---

### Task 2.3 — Verify connection from Python

```bash
cd backend
source venv/bin/activate
python -c "
import psycopg2
conn = psycopg2.connect(
    dbname='zerorespondnd',
    user='zr',
    password='secret',
    host='localhost',
    port=5432
)
print('Connection successful:', conn.status)
conn.close()
"
```

Expected output: `Connection successful: 1`

If this fails, check Docker is running and port 5432 is not blocked by another process.

---

## Day 3 — FastAPI Project Skeleton + Database Config

### Task 3.1 — Create backend/app/**init**.py

```bash
touch backend/app/__init__.py
touch backend/app/models/__init__.py
touch backend/app/routers/__init__.py
touch backend/app/services/__init__.py
touch backend/app/schemas/__init__.py
```

---

### Task 3.2 — Create backend/app/config.py

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    wazuh_url: str = ""
    wazuh_user: str = ""
    wazuh_pass: str = ""
    secret_key: str = "dev-secret-change-in-production"
    environment: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

### Task 3.3 — Create backend/app/database.py

```python
# backend/app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,       # Reconnect on stale connections
    pool_size=5,              # 5 connections in pool
    max_overflow=10,          # Up to 10 overflow connections
    echo=settings.environment == "development"  # Log SQL in dev only
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

### Task 3.4 — Create backend/app/main.py (skeleton only)

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": "development"
    }
```

Test the server boots:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
# Should output: Uvicorn running on http://127.0.0.1:8000
```

Open [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) — should return `{"status":"ok"}`.
Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — FastAPI Swagger UI should load.

Commit:

```bash
git add backend/
git commit -m "feat: fastapi skeleton with health endpoint and db config"
```

---

## Day 4 — SQLAlchemy Models (All 7 Tables)

This is the most important day of Week 1. Every decision you make here affects everything downstream. Think carefully before typing.

---

### Task 4.1 — Create backend/app/models/base.py

```python
# backend/app/models/base.py
# Import this in each model file to access the shared Base
from app.database import Base
```

---

### Task 4.2 — Create backend/app/models/org_profile.py

```python
# backend/app/models/org_profile.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.models.base import Base

class OrgProfile(Base):
    __tablename__ = "org_profile"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(255), nullable=False)
    dpo_name        = Column(String(255), nullable=False)   # Data Protection Officer
    dpo_email       = Column(String(255), nullable=False)
    address         = Column(String(500), nullable=True)
    cert_in_email   = Column(String(255), default="incident@cert-in.org.in")
    cert_in_notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())
```

---

### Task 4.3 — Create backend/app/models/alert.py

```python
# backend/app/models/alert.py
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.models.base import Base

class Alert(Base):
    __tablename__ = "alerts"

    id              = Column(String(50), primary_key=True)  # wazuh alert ID
    wazuh_rule_id   = Column(Integer, nullable=False)
    level           = Column(Integer, nullable=False)        # Wazuh severity level 1-15
    description     = Column(String(500), nullable=False)
    source_ip       = Column(String(45), nullable=True)      # IPv4 or IPv6
    host            = Column(String(255), nullable=False)
    groups          = Column(JSON, nullable=True)             # ["authentication_failed", "sshd"]
    attack_type     = Column(String(50), nullable=True)      # Set after AI classification
    raw_json        = Column(JSON, nullable=False)            # Full Wazuh alert payload
    received_at     = Column(DateTime(timezone=True), server_default=func.now())
```

---

### Task 4.4 — Create backend/app/models/playbook.py

```python
# backend/app/models/playbook.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base

class Playbook(Base):
    __tablename__ = "playbooks"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    attack_type = Column(String(50), unique=True, nullable=False)  # must match Case.breach_type
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    steps       = relationship("PlaybookStep", back_populates="playbook",
                               order_by="PlaybookStep.step_number")


class PlaybookStep(Base):
    __tablename__ = "playbook_steps"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)     # What to do and why
    linux_cmd   = Column(Text, nullable=True)      # Exact Linux command
    windows_cmd = Column(Text, nullable=True)      # Exact Windows PowerShell command
    goal        = Column(String(255), nullable=True) # What this step achieves
    is_blocking = Column(Boolean, default=False)   # Must complete before next step

    playbook    = relationship("Playbook", back_populates="steps")
```

---

### Task 4.5 — Create backend/app/models/case.py

```python
# backend/app/models/case.py
import enum
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class SeverityEnum(str, enum.Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"

class StatusEnum(str, enum.Enum):
    open          = "open"
    investigating = "investigating"
    contained     = "contained"
    resolved      = "resolved"
    closed        = "closed"

class BreachTypeEnum(str, enum.Enum):
    ransomware          = "ransomware"
    phishing            = "phishing"
    unauthorized_access = "unauthorized_access"
    exfiltration        = "exfiltration"
    insider             = "insider"

class Case(Base):
    __tablename__ = "cases"

    # Identity
    id              = Column(String(30), primary_key=True)   # IR-YYYYMMDD-XXXX
    title           = Column(String(255), nullable=False)

    # Classification
    severity        = Column(Enum(SeverityEnum), nullable=False, default=SeverityEnum.medium)
    status          = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.open)
    breach_type     = Column(Enum(BreachTypeEnum), nullable=False)

    # DPDP Act 2023 Section 8(6) fields
    data_categories = Column(String(255), nullable=True)   # PII, Financial, Health, Credentials
    persons_affected= Column(Integer, nullable=True)
    breach_est_at   = Column(DateTime(timezone=True), nullable=True)  # Estimated breach start

    # Attack context
    source_host     = Column(String(255), nullable=True)
    source_ip       = Column(String(45), nullable=True)

    # Relationships
    alert_id        = Column(String(50), ForeignKey("alerts.id"), nullable=True)
    playbook_id     = Column(Integer, ForeignKey("playbooks.id"), nullable=True)
    assigned_to     = Column(String(255), nullable=True)

    # AI enrichment
    ai_summary      = Column(Text, nullable=True)
    ai_confidence   = Column(Float, nullable=True)           # 0.0 - 100.0
    ai_mitre        = Column(String(20), nullable=True)      # T1486, T1566, etc.
    immediate_action= Column(Text, nullable=True)            # AI-recommended first action

    # Responder notes
    notes           = Column(Text, nullable=True)

    # Timestamps (immutable audit trail — never update detected_at)
    detected_at     = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at     = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    playbook        = relationship("Playbook")
    alert           = relationship("Alert")
    steps           = relationship("CaseStep", back_populates="case")
    evidence        = relationship("Evidence", back_populates="case")
```

---

### Task 4.6 — Create backend/app/models/case_step.py

```python
# backend/app/models/case_step.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class CaseStep(Base):
    __tablename__ = "case_steps"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    case_id          = Column(String(30), ForeignKey("cases.id"), nullable=False)
    playbook_step_id = Column(Integer, ForeignKey("playbook_steps.id"), nullable=False)
    completed_by     = Column(String(255), nullable=True)
    completed_at     = Column(DateTime(timezone=True), nullable=True)

    case             = relationship("Case", back_populates="steps")
    playbook_step    = relationship("PlaybookStep")
```

---

### Task 4.7 — Create backend/app/models/evidence.py

```python
# backend/app/models/evidence.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base

class Evidence(Base):
    __tablename__ = "evidence"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    case_id     = Column(String(30), ForeignKey("cases.id"), nullable=False)
    filename    = Column(String(255), nullable=False)    # Original filename
    filepath    = Column(String(500), nullable=False)    # Path on disk
    description = Column(Text, nullable=True)            # What this file shows
    file_size   = Column(Integer, nullable=True)         # Bytes
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    case        = relationship("Case", back_populates="evidence")
```

---

### Task 4.8 — Update backend/app/models/**init**.py to import all models

```python
# backend/app/models/__init__.py
# Import all models here so Alembic can detect them for autogenerate
from app.models.org_profile import OrgProfile
from app.models.alert import Alert
from app.models.playbook import Playbook, PlaybookStep
from app.models.case import Case, SeverityEnum, StatusEnum, BreachTypeEnum
from app.models.case_step import CaseStep
from app.models.evidence import Evidence

__all__ = [
    "OrgProfile", "Alert", "Playbook", "PlaybookStep",
    "Case", "SeverityEnum", "StatusEnum", "BreachTypeEnum",
    "CaseStep", "Evidence"
]
```

Commit:

```bash
git add backend/app/models/
git commit -m "feat: add all 7 SQLAlchemy models (cases, alerts, playbooks, steps, evidence, org_profile)"
```

---

## Day 5 — Alembic Setup + Migration + Verification

### Task 5.1 — Initialize Alembic

```bash
cd backend
source venv/bin/activate
alembic init alembic
```

This creates `alembic/` folder with `alembic.ini` and `alembic/env.py`.

---

### Task 5.2 — Configure alembic.ini

Open `backend/alembic.ini`. Find the line:

```
sqlalchemy.url = driver://user:pass@localhost/dbname
```

Replace it with:

```
sqlalchemy.url = postgresql://zr:secret@localhost:5432/zerorespondnd
```

> Note: In production, this will be loaded from env. For now, hardcode for dev only.

---

### Task 5.3 — Configure alembic/env.py

Open `backend/alembic/env.py`. Replace the top section with:

```python
# backend/alembic/env.py
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Add backend/ to Python path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models import *   # CRITICAL: imports all models so Alembic detects them

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata   # This tells Alembic what tables exist

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

### Task 5.4 — Generate the initial migration

```bash
cd backend
alembic revision --autogenerate -m "initial_schema"
```

Expected output:

```
Generating /backend/alembic/versions/xxxxxxxxxxxx_initial_schema.py ... done
```

Open the generated file in `alembic/versions/`. Verify it contains `op.create_table(...)` calls for all 7 tables:

- `org_profile`
- `alerts`
- `playbooks`
- `playbook_steps`
- `cases`
- `case_steps`
- `evidence`

If any table is missing, check that `backend/app/models/__init__.py` imports that model.

---

### Task 5.5 — Run the migration

```bash
alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Running upgrade  -> xxxxxxxxxxxx, initial_schema
```

---

### Task 5.6 — Verify all 7 tables exist in PostgreSQL

```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd -c "\dt"
```

Expected output:

```
            List of relations
 Schema |     Name      | Type  | Owner
--------+---------------+-------+-------
 public | alerts        | table | zr
 public | case_steps    | table | zr
 public | cases         | table | zr
 public | evidence      | table | zr
 public | org_profile   | table | zr
 public | playbook_steps| table | zr
 public | playbooks     | table | zr
(7 rows)
```

Verify column structure of the most important table:

```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd -c "\d cases"
```

Make sure all columns are present with the correct types.

Commit:

```bash
git add backend/alembic/
git commit -m "feat: alembic config + initial schema migration — all 7 tables"
```

---

## Day 6 — Ollama Setup + Connection Verification

### Task 6.1 — Install Ollama on your development machine

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

Verify installation:

```bash
ollama --version
```

---

### Task 6.2 — Pull the recommended model

```bash
ollama pull qwen2.5:7b
```

This downloads ~4.5GB. While it downloads, move to Task 6.3.

> **Why qwen2.5:7b?** It produces the most reliable structured JSON output of all 7B models. This matters because your AI agent depends on the LLM returning valid JSON every time.

---

### Task 6.3 — Verify Ollama is running

```bash
ollama serve &   # Start Ollama server in background (may already be running)
curl http://localhost:11434/api/tags
```

Should return a JSON list of available models including `qwen2.5:7b`.

---

### Task 6.4 — Test the model with a classification prompt

```bash
curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "stream": false,
    "messages": [
      {
        "role": "system",
        "content": "You are a cybersecurity AI. Respond ONLY with valid JSON, no markdown."
      },
      {
        "role": "user",
        "content": "Alert: SSH brute force, 500 failed logins in 2 minutes from IP 203.0.113.42 on host webserver01. Rule level 12. Classify this. Return JSON with keys: attack_type, severity_score, summary, confidence."
      }
    ],
    "options": { "temperature": 0.1 }
  }'
```

Expected: the model returns a JSON object. The `message.content` field should be parseable JSON. If it returns markdown backticks around the JSON, note this — your `ai_agent.py` will need to strip them.

---

### Task 6.5 — Create backend/app/services/ollama_client.py

```python
# backend/app/services/ollama_client.py
import httpx
import json
import re
from app.config import settings

async def call_ollama(system_prompt: str, user_message: str) -> str:
    """
    Send a prompt to local Ollama and return the response text.
    Raises httpx.HTTPError on connection failure.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": settings.ollama_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message}
                ],
                "options": {"temperature": 0.1, "num_predict": 500}
            }
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

def parse_llm_json(raw: str) -> dict:
    """
    Safely parse JSON from LLM output.
    Handles cases where the model wraps JSON in markdown code blocks.
    """
    # Strip markdown code fences if present: ```json ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    return json.loads(cleaned)
```

Test it manually:

```bash
cd backend
source venv/bin/activate
python -c "
import asyncio
from app.services.ollama_client import call_ollama, parse_llm_json

async def test():
    raw = await call_ollama(
        'You are a cybersecurity AI. Respond ONLY with valid JSON.',
        'SSH brute force attack, 500 logins in 2 minutes. Return JSON with: attack_type, severity_score (1-10), summary, confidence (0-100).'
    )
    print('Raw:', raw[:200])
    parsed = parse_llm_json(raw)
    print('Parsed:', parsed)

asyncio.run(test())
"
```

Commit:

```bash
git add backend/app/services/ollama_client.py
git commit -m "feat: ollama client with JSON parsing and markdown stripping"
```

---

## Day 7 — Final Verification + Week 1 Completion Check

### Task 7.1 — Full stack boot test

Open 3 terminals:

**Terminal 1 — PostgreSQL (already running in Docker):**

```bash
docker ps | grep zr-postgres
# Should show: Up X minutes
```

**Terminal 2 — Ollama:**

```bash
ollama serve
# Should show: Listening on 127.0.0.1:11434
```

**Terminal 3 — FastAPI:**

```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload
```

---

### Task 7.2 — Run the Week 1 completion checklist

Run each check and confirm it passes before calling Week 1 done:

```bash
# Check 1: All 7 tables exist
docker exec -it zr-postgres psql -U zr -d zerorespondnd -c "\dt" | grep -c "table"
# Expected output: 7

# Check 2: FastAPI health endpoint
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"1.0.0","environment":"development"}

# Check 3: Ollama responds
curl http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print('Models:', [m['name'] for m in d.get('models',[])])"
# Expected: Models: ['qwen2.5:7b']

# Check 4: Alembic migration is current
cd backend && alembic current
# Expected: xxxxxxxxxxxx (head)

# Check 5: Python imports work cleanly
python -c "from app.models import Case, Alert, Playbook, PlaybookStep, CaseStep, Evidence, OrgProfile; print('All 7 models imported OK')"
# Expected: All 7 models imported OK
```

---

### Task 7.3 — Final commit and tag

```bash
git add .
git commit -m "feat: week 1 complete — db schema, fastapi skeleton, ollama client"
git tag v0.1.0-week1
```

---

## Week 1 Summary


| Day | What you built                                               | Verification                             |
| --- | ------------------------------------------------------------ | ---------------------------------------- |
| 1   | Project structure, Git, Python venv, all dependencies, .env  | `pip freeze` shows all packages          |
| 2   | PostgreSQL in Docker with persistent volume                  | `docker exec psql` connects successfully |
| 3   | FastAPI skeleton, config, database.py, health endpoint       | `/health` returns 200, `/docs` loads     |
| 4   | All 7 SQLAlchemy models with correct types and relationships | All models import without errors         |
| 5   | Alembic configured, initial migration generated and applied  | `\dt` shows 7 tables in psql             |
| 6   | Ollama installed, qwen2.5:7b pulled, ollama_client.py tested | Model returns parseable JSON             |
| 7   | Full stack boots together, all 5 checklist items pass        | All checks green                         |


**You are now ready for Week 2 — Case Manager REST API.**

---

*ZeroRespond · Manikandan · KCT 2023–2027*