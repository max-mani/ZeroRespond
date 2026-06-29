# ZeroRespond — Week 6 Task List
**Phase 6 · Org Profile Settings + Playbooks + Docker Compose**

> **Goal by end of Week 6:** Three things done. First, an org profile API so client organisations can set their name, DPO details, and CERT-In contact — this makes DPDP reports contain real data instead of placeholders. Second, playbooks — structured step-by-step response guides for each of the 5 breach types, seeded with production-quality content and visible in the frontend. Third, a Docker Compose file that starts the entire stack (PostgreSQL + FastAPI + React + Nginx) with a single command — this is what you hand to a client for deployment.

---

## What you have coming in from Week 5

- JWT auth on all endpoints — `get_current_user` protecting cases, alerts, reports
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me` working
- DPDP PDF generation via WeasyPrint + Jinja2 template
- `OrgProfile` model already exists in `backend/app/models/org_profile.py`
- `Playbook` and `PlaybookStep` models already exist in `backend/app/models/playbook.py`
- `CaseStep` model already exists in `backend/app/models/case_step.py`
- Frontend: Login, Dashboard, Cases, Case Detail, Alert Feed — all working with auth
- `data/reports/` directory exists and is gitignored

---

## Week 6 Architecture

```
What you are building:

Backend:
  GET    /org                    ← get org profile
  PUT    /org                    ← update org profile (admin only)
  GET    /playbooks              ← list all playbooks
  GET    /playbooks/{attack_type} ← get playbook with steps for one breach type
  GET    /cases/{id}/playbook    ← get the playbook attached to a case
  POST   /cases/{id}/steps/{step_id}/complete ← mark a playbook step done

  New files:
  backend/app/
  ├── schemas/
  │   ├── org.py                 ← OrgProfileOut, OrgProfileUpdate
  │   └── playbook.py            ← PlaybookOut, PlaybookStepOut
  ├── routers/
  │   ├── org.py                 ← GET /org, PUT /org
  │   └── playbooks.py           ← GET /playbooks, GET /playbooks/{attack_type}
  └── scripts/
      └── seed_playbooks.py      ← 5 playbooks with full step content

Frontend:
  New/updated files:
  frontend/src/
  ├── pages/
  │   └── PlaybookPage.tsx       ← Playbook steps viewer for a case
  ├── components/
  │   └── playbook/
  │       └── PlaybookRunner.tsx ← Step-by-step checklist with complete button
  └── api/
      └── client.ts              ← add getPlaybook(), completeStep(), updateOrg()

Docker:
  docker-compose.yml             ← full stack: postgres + backend + frontend + nginx
  nginx/
  └── nginx.conf                 ← reverse proxy config
  frontend/
  └── Dockerfile                 ← multi-stage React build
  backend/
  └── Dockerfile                 ← FastAPI production container
```

---

## Day 1 — Org Profile API

The `OrgProfile` model already exists from Week 1. Today you build the API on top of it so organisations can update their details through the UI instead of running Python scripts directly.

---

### Task 1.1 — Create backend/app/schemas/org.py

```python
# backend/app/schemas/org.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class OrgProfileOut(BaseModel):
    """Returned by GET /org."""
    id:                  int
    name:                str
    dpo_name:            str
    dpo_email:           str
    address:             Optional[str]
    cert_in_email:       str
    cert_in_notified_at: Optional[datetime]
    created_at:          datetime
    updated_at:          Optional[datetime]

    model_config = {"from_attributes": True}


class OrgProfileUpdate(BaseModel):
    """
    Used by PUT /org to update org details.
    All fields are optional — send only what you want to change.
    """
    name:          Optional[str] = Field(None, min_length=2, max_length=255)
    dpo_name:      Optional[str] = Field(None, min_length=2, max_length=255)
    dpo_email:     Optional[str] = Field(None, max_length=255)
    address:       Optional[str] = Field(None, max_length=500)
    cert_in_email: Optional[str] = Field(None, max_length=255)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Coimbatore Medical College Hospital",
                "dpo_name": "Dr. Manikandan",
                "dpo_email": "dpo@cmch.edu.in",
                "address": "Coimbatore, Tamil Nadu 641 014",
                "cert_in_email": "incident@cert-in.org.in"
            }
        }
```

---

### Task 1.2 — Create backend/app/routers/org.py

```python
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
```

---

### Task 1.3 — Register org router in main.py

```python
# backend/app/main.py
from app.routers import alerts, cases, auth, reports, org   # ← add org

# Add after existing routers:
app.include_router(org.router)
```

---

### Task 1.4 — Test the org endpoints

```bash
TOKEN="eyJ..."   # your admin token

# Set org profile
curl -X PUT http://localhost:8000/org \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Coimbatore Medical College Hospital",
    "dpo_name": "Dr. Manikandan",
    "dpo_email": "dpo@cmch.edu.in",
    "address": "Coimbatore, Tamil Nadu 641 014",
    "cert_in_email": "incident@cert-in.org.in"
  }'
# Expected: 200 with org profile

# Read it back
curl http://localhost:8000/org \
  -H "Authorization: Bearer $TOKEN"
# Expected: same org profile

# Generate a DPDP report — should now show real org name
curl -X POST http://localhost:8000/reports/IR-20260623-0003 \
  -H "Authorization: Bearer $TOKEN" \
  --output /tmp/report_with_org.pdf
xdg-open /tmp/report_with_org.pdf
# Expected: PDF header shows "Coimbatore Medical College Hospital"

# Analyst cannot update org
ANALYST_TOKEN="eyJ..."
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X PUT http://localhost:8000/org \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANALYST_TOKEN" \
  -d '{"name": "Hacked"}')
[ "$RESP" = "403" ] && echo "✓ Analyst blocked from updating org" || echo "✗ Expected 403, got $RESP"
```

Commit:
```bash
git add backend/app/schemas/org.py backend/app/routers/org.py backend/app/main.py
git commit -m "feat: org profile API — GET /org, PUT /org (admin only)"
```

---

## Day 2 — Playbook Schemas + Router

The `Playbook` and `PlaybookStep` models exist from Week 1. Today you build the API to read them.

---

### Task 2.1 — Create backend/app/schemas/playbook.py

```python
# backend/app/schemas/playbook.py
from pydantic import BaseModel
from typing import Optional, List

class PlaybookStepOut(BaseModel):
    """One step in a playbook."""
    id:          int
    step_number: int
    title:       str
    description: str
    linux_cmd:   Optional[str]
    windows_cmd: Optional[str]
    goal:        Optional[str]
    is_blocking: bool

    model_config = {"from_attributes": True}


class PlaybookOut(BaseModel):
    """Full playbook with all steps."""
    id:          int
    attack_type: str
    name:        str
    description: Optional[str]
    steps:       List[PlaybookStepOut]

    model_config = {"from_attributes": True}


class PlaybookListItem(BaseModel):
    """Compact playbook for list view — no steps."""
    id:          int
    attack_type: str
    name:        str
    description: Optional[str]

    model_config = {"from_attributes": True}


class CaseStepOut(BaseModel):
    """Tracks completion of a playbook step for a specific case."""
    id:               int
    playbook_step_id: int
    completed_by:     Optional[str]
    completed_at:     Optional[str]
    playbook_step:    PlaybookStepOut

    model_config = {"from_attributes": True}
```

---

### Task 2.2 — Create backend/app/routers/playbooks.py

```python
# backend/app/routers/playbooks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app.models.playbook import Playbook, PlaybookStep
from app.models.case import Case
from app.models.case_step import CaseStep
from app.schemas.playbook import PlaybookOut, PlaybookListItem, CaseStepOut
from app.services.auth_service import get_current_user
from app.models.user import User

router = APIRouter(prefix="/playbooks", tags=["Playbooks"])


@router.get(
    "",
    response_model=List[PlaybookListItem],
    summary="List all playbooks (one per breach type)"
)
def list_playbooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Playbook]:
    return db.query(Playbook).order_by(Playbook.attack_type).all()


@router.get(
    "/{attack_type}",
    response_model=PlaybookOut,
    summary="Get full playbook with steps for a breach type",
    description="attack_type must be one of: ransomware, phishing, unauthorized_access, exfiltration, insider"
)
def get_playbook(
    attack_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Playbook:
    playbook = db.query(Playbook).filter(Playbook.attack_type == attack_type).first()
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No playbook found for attack type '{attack_type}'. "
                   f"Valid types: ransomware, phishing, unauthorized_access, exfiltration, insider"
        )
    return playbook


# ─── Case-specific playbook endpoints ─────────────────────────────────────────

cases_router = APIRouter(prefix="/cases", tags=["Playbooks"])


@cases_router.get(
    "/{case_id}/playbook",
    response_model=PlaybookOut,
    summary="Get the playbook for a specific case based on its breach type"
)
def get_case_playbook(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Playbook:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )

    playbook = db.query(Playbook).filter(
        Playbook.attack_type == case.breach_type.value
    ).first()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No playbook found for breach type '{case.breach_type.value}'"
        )
    return playbook


@cases_router.post(
    "/{case_id}/steps/{step_id}/complete",
    response_model=CaseStepOut,
    summary="Mark a playbook step as completed for a case"
)
def complete_step(
    case_id: str,
    step_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> CaseStep:
    # Verify case exists
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Verify step exists
    step = db.query(PlaybookStep).filter(PlaybookStep.id == step_id).first()
    if not step:
        raise HTTPException(status_code=404, detail=f"Playbook step {step_id} not found")

    # Check if already completed
    existing = db.query(CaseStep).filter(
        CaseStep.case_id == case_id,
        CaseStep.playbook_step_id == step_id
    ).first()

    if existing:
        return existing   # Idempotent — return existing completion record

    # Create completion record
    case_step = CaseStep(
        case_id=case_id,
        playbook_step_id=step_id,
        completed_by=current_user.email,
        completed_at=datetime.now(timezone.utc)
    )
    db.add(case_step)
    db.commit()
    db.refresh(case_step)
    return case_step
```

---

### Task 2.3 — Register both routers in main.py

```python
# backend/app/main.py
from app.routers import alerts, cases, auth, reports, org, playbooks  # ← add playbooks

# Add after existing routers:
app.include_router(playbooks.router)
app.include_router(playbooks.cases_router)   # ← mounts at /cases/{id}/playbook
```

Commit:
```bash
git add backend/app/schemas/playbook.py backend/app/routers/playbooks.py backend/app/main.py
git commit -m "feat: playbooks router — list, get by attack type, get for case, complete step"
```

---

## Day 3 — Seed Playbooks with Real Content

This is the most important day of Week 6. Empty playbooks are useless. Every step must be concrete enough that a non-security IT administrator at a college or hospital can follow it without calling anyone.

---

### Task 3.1 — Create backend/scripts/seed_playbooks.py

```python
#!/usr/bin/env python3
# backend/scripts/seed_playbooks.py
"""
Seeds 5 production-quality playbooks covering all breach types.
Each playbook has 6-8 steps with exact Linux commands.
Usage: cd backend && python scripts/seed_playbooks.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.playbook import Playbook, PlaybookStep

PLAYBOOKS = [

    # ─── 1. RANSOMWARE ────────────────────────────────────────────────────────
    {
        "attack_type": "ransomware",
        "name": "Ransomware Response Playbook",
        "description": "Structured response for file-encrypting ransomware. Speed is critical — every minute of delay allows more files to be encrypted and increases recovery cost.",
        "steps": [
            {
                "step_number": 1,
                "title": "Isolate the infected host immediately",
                "description": "Disconnect the infected machine from the network to stop ransomware from spreading to shared drives, backup servers, and other hosts. Do NOT shut down the machine — RAM may contain decryption keys that forensics can recover.",
                "linux_cmd": "# On the infected Linux host:\nsudo ip link set eth0 down\n# OR physically unplug the network cable\n# Verify isolation:\nip addr show",
                "windows_cmd": "# Disable network adapter in Windows:\nDisable-NetAdapter -Name 'Ethernet' -Confirm:$false\n# Verify:\nGet-NetAdapter | Select Name, Status",
                "goal": "Stop lateral movement to other systems",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Preserve memory and disk evidence",
                "description": "Before any remediation, capture the system state. This is required for forensics and insurance claims. Use a USB drive or network share that is NOT connected to the infected machine.",
                "linux_cmd": "# Capture memory dump (requires LiME or avml):\nsudo avml /external-usb/memory_dump.lime\n\n# List running processes before shutdown:\nps aux > /external-usb/process_list.txt\nnetstat -tulpn > /external-usb/network_connections.txt\n\n# Note encrypted file extensions:\nfind /home /var /srv -name '*.enc' -o -name '*.locked' | head -50",
                "windows_cmd": "# Save process list:\nGet-Process | Export-Csv C:\\evidence\\processes.csv\nGet-NetTCPConnection | Export-Csv C:\\evidence\\connections.csv\n\n# Note ransom note location:\nGet-ChildItem C:\\ -Recurse -Filter 'READ_ME*' 2>$null | Select FullName",
                "goal": "Preserve forensic evidence before remediation",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Identify the ransomware strain",
                "description": "Identifying the specific strain determines whether a free decryptor exists. Upload a ransom note or encrypted file sample to ID Ransomware (https://id-ransomware.malwarehunterteam.com). Check No More Ransom (https://www.nomoreransom.org) for free decryptors before paying anything.",
                "linux_cmd": "# Check ransom note for strain indicators:\ncat /path/to/README_FOR_DECRYPT.txt\n\n# Check encrypted file extension:\nls /affected-directory/ | head -20\n\n# Check for known strain IOCs in logs:\ngrep -r 'ransom\\|encrypt\\|bitcoin' /var/log/ 2>/dev/null | tail -20",
                "windows_cmd": "# Find ransom notes:\nGet-ChildItem C:\\ -Recurse -Include 'README*','DECRYPT*','HOW_TO*' 2>$null\n\n# Check event logs for suspicious activity:\nGet-EventLog -LogName System -Newest 100 | Where-Object {$_.EntryType -eq 'Error'}",
                "goal": "Determine if a free decryptor exists before considering payment",
                "is_blocking": False
            },
            {
                "step_number": 4,
                "title": "Check and protect backups",
                "description": "Immediately verify your backups are clean and not encrypted. Ransomware specifically targets backup systems. Isolate clean backups from the network immediately.",
                "linux_cmd": "# Check backup server is reachable and clean:\nssh backup-server 'ls -lh /backups/ | tail -20'\n\n# Verify backup integrity (example with rsync):\nrsync --dry-run --checksum /backups/latest/ /tmp/verify/\n\n# Check if backup files show recent modification (sign of encryption):\nfind /backup-mount -newer /tmp/reference_file -type f | head -20",
                "windows_cmd": "# Check Windows Backup / Veeam status:\nGet-WBJob\n\n# List recent backup jobs:\nGet-WBBackupSet | Sort-Object BackupTime -Descending | Select -First 5",
                "goal": "Ensure clean backups exist for recovery",
                "is_blocking": True
            },
            {
                "step_number": 5,
                "title": "Notify management and legal",
                "description": "Under DPDP Act 2023, if personal data is affected, CERT-In must be notified within 6 hours of discovery. Notify your DPO, legal team, and senior management immediately. Do not communicate over email if email servers may be compromised — use phone.",
                "linux_cmd": "# Generate the DPDP breach notification from ZeroRespond:\ncurl -X POST http://localhost:8000/reports/<CASE_ID> \\\n  -H 'Authorization: Bearer <TOKEN>' \\\n  --output DPDP_Notification.pdf\n\n# Email to CERT-In: incident@cert-in.org.in\n# Subject: Cyber Security Incident Report — [Organisation Name]",
                "windows_cmd": "# Same curl command works from Windows PowerShell:\nInvoke-WebRequest -Uri 'http://localhost:8000/reports/<CASE_ID>' \\\n  -Headers @{Authorization='Bearer <TOKEN>'} \\\n  -OutFile DPDP_Notification.pdf",
                "goal": "Meet DPDP Act 2023 6-hour notification requirement",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Restore from clean backup",
                "description": "Once the infected system is isolated and evidence preserved, restore from the last known-clean backup. Rebuild the OS from scratch rather than restoring to the same infected system — ransomware may have persistence mechanisms.",
                "linux_cmd": "# Wipe and reinstall OS, then restore data:\n# 1. Boot from clean media\n# 2. Reinstall OS\n# 3. Restore data backup:\nrsync -avz --progress backup-server:/backups/pre-infection/ /restored-data/\n\n# Verify restored files:\nmd5sum /restored-data/critical-files/* > checksums.txt",
                "windows_cmd": "# Restore from backup:\nStart-WBFileRecovery -BackupSet (Get-WBBackupSet | Select -Last 1) \\\n  -FilePathToRestore 'C:\\Data' -RecoveryTarget 'D:\\Restored'",
                "goal": "Restore operations from clean backup",
                "is_blocking": True
            },
            {
                "step_number": 7,
                "title": "Post-incident hardening",
                "description": "After recovery, implement controls to prevent recurrence. Ransomware most commonly enters via unpatched systems, RDP exposed to internet, or phishing emails.",
                "linux_cmd": "# Update all packages:\nsudo apt update && sudo apt upgrade -y\n\n# Disable unused services:\nsudo systemctl disable telnet ftp rsh\n\n# Check for exposed RDP/SMB ports:\nss -tulpn | grep -E ':3389|:445|:139'\n\n# Enable automatic security updates:\nsudo dpkg-reconfigure -plow unattended-upgrades",
                "windows_cmd": "# Check Windows Update status:\nGet-WindowsUpdateLog\n\n# Disable RDP if not needed:\nSet-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name 'fDenyTSConnections' -Value 1\n\n# Enable Windows Defender:\nSet-MpPreference -DisableRealtimeMonitoring $false",
                "goal": "Prevent ransomware recurrence",
                "is_blocking": False
            }
        ]
    },

    # ─── 2. PHISHING ──────────────────────────────────────────────────────────
    {
        "attack_type": "phishing",
        "name": "Phishing Attack Response Playbook",
        "description": "Response for phishing attacks including credential harvesting, malicious links, and email-delivered malware. Focus on containing the blast radius and preventing credential reuse.",
        "steps": [
            {
                "step_number": 1,
                "title": "Identify affected users and scope",
                "description": "Determine who received the phishing email, who clicked the link, and who may have entered credentials. Pull mail server logs immediately — email logs are often overwritten within 24-72 hours.",
                "linux_cmd": "# Pull mail server logs (Postfix example):\ngrep 'phishing-domain.com' /var/log/mail.log | grep 'delivered'\n\n# Check web proxy logs for clicks on malicious URL:\ngrep 'malicious-url.com' /var/log/squid/access.log\n\n# List all users who accessed the malicious URL:\nawk '{print $8}' /var/log/squid/access.log | grep 'malicious' | sort | uniq",
                "windows_cmd": "# Search Exchange mail logs:\nGet-MessageTrackingLog -ResultSize Unlimited -MessageSubject 'phishing subject' | Select Sender, Recipients, Timestamp\n\n# Search for URL clicks in Exchange:\nGet-MessageTrackingLog -EventId DELIVER | Where-Object {$_.Recipients -like '*finance*'}",
                "goal": "Know exactly who was targeted and who interacted with the phishing content",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Block the malicious URL and sender domain",
                "description": "Immediately block the phishing URL and sender domain at the email gateway and web proxy. This stops anyone else in the organisation from clicking the link.",
                "linux_cmd": "# Block domain at DNS level (add to /etc/hosts on DNS server or Pi-hole):\necho '0.0.0.0 malicious-domain.com' | sudo tee -a /etc/hosts\n\n# Block in UFW firewall:\nsudo ufw deny out to any port 80,443 comment 'block phishing domain'\n\n# Add to email blacklist (Postfix):\necho 'malicious-sender@phishing.com REJECT Phishing attempt' >> /etc/postfix/sender_access\npostmap /etc/postfix/sender_access\nsudo systemctl reload postfix",
                "windows_cmd": "# Block URL in Windows Defender SmartScreen or proxy:\nAdd-MpPreference -ExclusionPath 'N/A'  # Use Windows Firewall\nNew-NetFirewallRule -DisplayName 'Block Phishing' -Direction Outbound -Action Block -RemoteAddress 'phishing-ip'",
                "goal": "Prevent further exposure across the organisation",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Force password reset for all affected users",
                "description": "Any user who may have entered credentials on the phishing page must reset their password immediately. Also revoke all active sessions for those accounts.",
                "linux_cmd": "# Force password change on next login (Linux/LDAP):\npasswd -e username\n\n# For multiple users from a file:\nwhile read user; do passwd -e \"$user\"; done < affected_users.txt\n\n# Revoke SSH keys if compromised:\nrm /home/username/.ssh/authorized_keys\n\n# Check for new SSH keys added by attacker:\nfind /home -name 'authorized_keys' -newer /tmp/reference_date -ls",
                "windows_cmd": "# Force password reset in Active Directory:\nSet-ADUser -Identity 'username' -ChangePasswordAtLogon $true\n\n# Revoke all active sessions:\nRevoke-MgUserSignInSession -UserId 'user@domain.com'\n\n# Bulk reset from list:\nGet-Content affected_users.txt | ForEach-Object { Set-ADUser $_ -ChangePasswordAtLogon $true }",
                "goal": "Neutralise harvested credentials before attackers use them",
                "is_blocking": True
            },
            {
                "step_number": 4,
                "title": "Check for account compromise and lateral movement",
                "description": "Review authentication logs for the affected accounts. Look for logins from unusual IPs, at unusual times, or to systems they do not normally access.",
                "linux_cmd": "# Check auth logs for suspicious logins:\ngrep 'Accepted password' /var/log/auth.log | grep 'username'\n\n# Look for logins from foreign IPs:\ngrep 'Accepted' /var/log/auth.log | awk '{print $11}' | sort | uniq -c | sort -rn\n\n# Check for privilege escalation attempts:\ngrep 'sudo\\|su ' /var/log/auth.log | grep 'username'",
                "windows_cmd": "# Check Windows event logs for suspicious logons (Event ID 4624):\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} | Where-Object {$_.Message -like '*username*'} | Select TimeCreated, Message | Select -First 20\n\n# Look for logons from unusual locations:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4625} | Select -First 50",
                "goal": "Determine if attacker already used the harvested credentials",
                "is_blocking": False
            },
            {
                "step_number": 5,
                "title": "Enable MFA for all affected accounts",
                "description": "Password reset alone is not enough if the attacker still has the old password. Enable multi-factor authentication on all affected accounts before they log back in.",
                "linux_cmd": "# Enable Google Authenticator for SSH (PAM):\nsudo apt install libpam-google-authenticator\n\n# Configure PAM:\necho 'auth required pam_google_authenticator.so' | sudo tee -a /etc/pam.d/sshd\n\n# Update SSH config:\necho 'ChallengeResponseAuthentication yes' | sudo tee -a /etc/ssh/sshd_config\nsudo systemctl restart sshd",
                "windows_cmd": "# Enable MFA via Microsoft 365 / Azure AD:\nSet-MsolUser -UserPrincipalName 'user@domain.com' -StrongAuthenticationRequirements @(New-Object -TypeName Microsoft.Online.Administration.StrongAuthenticationRequirement)",
                "goal": "Prevent future credential reuse even if attacker retains the password",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Report phishing email to CERT-In and conduct user awareness",
                "description": "Report the phishing campaign to CERT-In (incident@cert-in.org.in) with the full email headers and malicious URL. Run an immediate awareness session with staff about the specific phishing technique used.",
                "linux_cmd": "# Generate DPDP report:\ncurl -X POST http://localhost:8000/reports/<CASE_ID> \\\n  -H 'Authorization: Bearer <TOKEN>' \\\n  --output DPDP_Phishing_Report.pdf\n\n# Save full email headers for CERT-In submission:\ncat /var/mail/username | head -100 > phishing_email_headers.txt",
                "windows_cmd": "# Export phishing email from Outlook:\n# File > Open & Export > Import/Export > Export to a File > Outlook Data File (.pst)",
                "goal": "Meet reporting obligations and prevent recurrence",
                "is_blocking": False
            }
        ]
    },

    # ─── 3. UNAUTHORIZED ACCESS ───────────────────────────────────────────────
    {
        "attack_type": "unauthorized_access",
        "name": "Unauthorised Access Response Playbook",
        "description": "Response for brute force attacks, authentication bypass, and unauthorised login attempts. Focus on blocking the attacker, assessing damage, and hardening access controls.",
        "steps": [
            {
                "step_number": 1,
                "title": "Block the attacking IP immediately",
                "description": "Block the source IP at the firewall and on the affected host. If the attacker is using multiple IPs (distributed brute force), block the entire subnet.",
                "linux_cmd": "# Block single IP:\nsudo ufw deny from 203.0.113.42 to any\n# OR with iptables:\nsudo iptables -A INPUT -s 203.0.113.42 -j DROP\n\n# Block entire subnet if distributed attack:\nsudo ufw deny from 203.0.113.0/24 to any\n\n# Verify block:\nsudo ufw status numbered\n\n# Install and use fail2ban for automatic blocking:\nsudo apt install fail2ban\nsudo systemctl enable fail2ban --now",
                "windows_cmd": "# Block IP in Windows Firewall:\nNew-NetFirewallRule -DisplayName 'Block Attacker' -Direction Inbound -Action Block -RemoteAddress '203.0.113.42'\n\n# Verify:\nGet-NetFirewallRule -DisplayName 'Block Attacker'",
                "goal": "Stop the ongoing attack immediately",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Determine if any login was successful",
                "description": "A brute force attack is low impact if no login succeeded. Check authentication logs very carefully for any 'Accepted' entries from the attacking IP before the block took effect.",
                "linux_cmd": "# Check for successful logins from the attacker IP:\ngrep 'Accepted' /var/log/auth.log | grep '203.0.113.42'\n\n# Check all successful logins in the attack window:\ngrep 'Accepted password\\|Accepted publickey' /var/log/auth.log | \\\n  awk '{print $1, $2, $3, $9, $11}'\n\n# Check for any new users created recently (attacker persistence):\ngrep 'new user\\|useradd\\|adduser' /var/log/auth.log\nawk -F: '$3 > 1000 {print $1, $3}' /etc/passwd",
                "windows_cmd": "# Search for successful logons from attacking IP:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} | \\\n  Where-Object {$_.Message -like '*203.0.113.42*'} | Select TimeCreated, Message\n\n# Check for new accounts created:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4720} | Select -First 10",
                "goal": "Determine if the attacker gained access — this changes the severity of the response",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Review and strengthen password policy",
                "description": "Brute force succeeds because of weak passwords. Check what accounts were targeted and enforce stronger passwords immediately.",
                "linux_cmd": "# Install and configure password quality checking:\nsudo apt install libpam-pwquality\n\n# Configure /etc/security/pwquality.conf:\nminlen = 12\ndcredit = -1\nucredit = -1\nocredit = -1\nlcredit = -1\n\n# Check accounts with empty or no password:\nsudo awk -F: '($2 == \"\" || $2 == \"!\") {print $1}' /etc/shadow\n\n# Check for accounts with no password expiry:\nsudo chage -l username",
                "windows_cmd": "# Set password policy via Group Policy or local policy:\nnet accounts /minpwlen:12 /maxpwage:90 /uniquepw:5\n\n# Check current password policy:\nnet accounts",
                "goal": "Close the vulnerability that allowed the brute force attempt",
                "is_blocking": False
            },
            {
                "step_number": 4,
                "title": "Restrict SSH / RDP to known IPs only",
                "description": "SSH and RDP should never be open to the entire internet. Restrict access to specific IP ranges or implement a VPN for remote access.",
                "linux_cmd": "# Restrict SSH to specific IPs only:\nsudo ufw allow from 10.0.0.0/8 to any port 22\nsudo ufw allow from 192.168.0.0/16 to any port 22\nsudo ufw deny 22\n\n# Change SSH to non-standard port:\nsudo sed -i 's/#Port 22/Port 2222/' /etc/ssh/sshd_config\nsudo systemctl restart sshd\n\n# Disable password auth — use keys only:\nsudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config",
                "windows_cmd": "# Restrict RDP to internal network only:\nNew-NetFirewallRule -DisplayName 'RDP Internal Only' -Direction Inbound -LocalPort 3389 -Protocol TCP -RemoteAddress '10.0.0.0/8' -Action Allow\nNew-NetFirewallRule -DisplayName 'Block RDP External' -Direction Inbound -LocalPort 3389 -Protocol TCP -Action Block",
                "goal": "Prevent future brute force from the internet",
                "is_blocking": False
            },
            {
                "step_number": 5,
                "title": "Configure automatic blocking with fail2ban",
                "description": "Fail2ban monitors auth logs and automatically blocks IPs after a configurable number of failed attempts. This provides ongoing protection without manual intervention.",
                "linux_cmd": "# Install fail2ban:\nsudo apt install fail2ban -y\n\n# Create local config:\nsudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local\n\n# Configure SSH jail in /etc/fail2ban/jail.local:\n[sshd]\nenabled = true\nport    = ssh\nfilter  = sshd\nlogpath = /var/log/auth.log\nmaxretry = 5\nbantime  = 3600\nfindtime = 600\n\n# Start and enable:\nsudo systemctl enable fail2ban --now\n\n# Check status:\nsudo fail2ban-client status sshd",
                "windows_cmd": "# Windows equivalent: configure Account Lockout Policy:\nnet accounts /lockoutthreshold:5 /lockoutduration:60 /lockoutwindow:10\n\n# Or use Windows Defender ATP for automatic blocking",
                "goal": "Automate protection against future brute force attempts",
                "is_blocking": False
            },
            {
                "step_number": 6,
                "title": "Enable two-factor authentication",
                "description": "Even if an attacker gets a valid password, 2FA stops them from logging in. Enable it on all internet-facing services.",
                "linux_cmd": "# Install Google Authenticator PAM module:\nsudo apt install libpam-google-authenticator -y\n\n# Run as each user to set up:\ngoogle-authenticator\n\n# Configure PAM for SSH:\necho 'auth required pam_google_authenticator.so' | sudo tee -a /etc/pam.d/sshd\necho 'AuthenticationMethods publickey,keyboard-interactive' | sudo tee -a /etc/ssh/sshd_config\nsudo systemctl restart sshd",
                "windows_cmd": "# Enable Azure MFA for all users:\nConnect-MsolService\nGet-MsolUser -All | Where-Object {$_.IsLicensed -eq $true} | ForEach-Object {\n  $Requirements = @()\n  $Requirements += New-Object -TypeName Microsoft.Online.Administration.StrongAuthenticationRequirement\n  Set-MsolUser -UserPrincipalName $_.UserPrincipalName -StrongAuthenticationRequirements $Requirements\n}",
                "goal": "Make stolen passwords useless without a second factor",
                "is_blocking": False
            }
        ]
    },

    # ─── 4. EXFILTRATION ──────────────────────────────────────────────────────
    {
        "attack_type": "exfiltration",
        "name": "Data Exfiltration Response Playbook",
        "description": "Response for suspected or confirmed data theft. Focus on stopping the transfer, determining what data left, and meeting DPDP Act 2023 notification requirements.",
        "steps": [
            {
                "step_number": 1,
                "title": "Block the outbound connection immediately",
                "description": "Stop the active data transfer. Block the destination IP and the source host's outbound internet access while preserving the system for forensics.",
                "linux_cmd": "# Block outbound to exfiltration destination:\nsudo ufw deny out to <destination-ip>\n\n# Block all outbound from the compromised host (drastic but effective):\nsudo iptables -I OUTPUT -j DROP\n\n# Capture the active connection before blocking:\nsudo ss -tulpn | grep ESTABLISHED\nsudo netstat -anp | grep '<destination-ip>' > /evidence/active_connections.txt\n\n# Capture network traffic dump:\nsudo tcpdump -i eth0 -w /evidence/capture.pcap host <destination-ip> &",
                "windows_cmd": "# Block outbound connection:\nNew-NetFirewallRule -DisplayName 'Block Exfil' -Direction Outbound -Action Block -RemoteAddress '<destination-ip>'\n\n# Capture traffic:\nnetsh trace start capture=yes tracefile=C:\\evidence\\capture.etl",
                "goal": "Stop data leaving the network immediately",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Quantify what data was transferred",
                "description": "Determine how much data left, to where, and what it may have contained. This is critical for DPDP reporting — you must estimate the number of persons affected.",
                "linux_cmd": "# Check network traffic volume to destination IP (from NetFlow or proxy logs):\ngrep '<destination-ip>' /var/log/squid/access.log | \\\n  awk '{sum += $5} END {print \"Total bytes transferred: \" sum}'\n\n# Check what files were recently accessed on the compromised host:\nfind /sensitive-data -type f -newer /tmp/reference_file -ls\n\n# Check database query logs:\ngrep 'SELECT.*FROM' /var/log/postgresql/postgresql.log | tail -100\n\n# Review bash history of compromised user:\ncat /home/username/.bash_history | grep -E 'curl|wget|scp|rsync|tar'",
                "windows_cmd": "# Check recent file access:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} | Select -First 50\n\n# Check PowerShell history:\nGet-Content (Get-PSReadlineOption).HistorySavePath | Select-String 'Invoke-WebRequest|curl|ftp'",
                "goal": "Establish what personal data may have been exfiltrated for DPDP reporting",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Identify and contain the exfiltration vector",
                "description": "Determine how data was being exfiltrated — web upload, email attachment, FTP, cloud sync, or physical media — and close that channel.",
                "linux_cmd": "# Check for active cloud sync clients:\nps aux | grep -E 'dropbox|onedrive|googledrive|rclone|rsync'\n\n# Check for scheduled tasks that may be exfiltrating data:\ncrontab -l\nsudo cat /etc/cron*\n\n# Check for unauthorised tools installed:\nwhich ncat nc socat curl wget | xargs ls -la\nfind / -name 'rclone' -o -name 'exfil*' 2>/dev/null\n\n# Check recently installed packages:\ndpkg --get-selections | grep -v deinstall | tail -20",
                "windows_cmd": "# Check for cloud sync:\nGet-Process | Where-Object {$_.Name -like '*drop*' -or $_.Name -like '*one*'}\n\n# Check scheduled tasks:\nGet-ScheduledTask | Where-Object {$_.State -eq 'Ready'} | Select TaskName, TaskPath",
                "goal": "Close the exfiltration channel and remove attacker tools",
                "is_blocking": True
            },
            {
                "step_number": 4,
                "title": "Determine root cause of compromise",
                "description": "How did the attacker get access to the system that was exfiltrating data? Look for the initial access vector — phishing email, compromised credential, unpatched vulnerability, or insider.",
                "linux_cmd": "# Review authentication logs for the days before exfiltration:\ngrep 'Accepted' /var/log/auth.log | grep -v 'known-good-ip'\n\n# Check for webshell or backdoor:\nfind /var/www -type f -name '*.php' -newer /tmp/reference_date\ngrep -r 'eval(base64_decode' /var/www/ 2>/dev/null\n\n# Check for new cron jobs or systemd services:\nls -la /etc/cron.d/ /etc/systemd/system/*.service | grep -v 'root'\n\n# Look for recently modified system files:\nfind /etc /bin /usr/bin -newer /tmp/reference_date -type f",
                "windows_cmd": "# Check for recently installed software:\nGet-WmiObject Win32_Product | Sort-Object InstallDate -Descending | Select -First 10\n\n# Review PowerShell execution logs:\nGet-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-PowerShell/Operational'} | Select -First 50",
                "goal": "Understand how the attacker got in so you can close the initial access vector",
                "is_blocking": False
            },
            {
                "step_number": 5,
                "title": "Notify affected data principals and CERT-In",
                "description": "Under DPDP Act 2023, data principals (the people whose data was stolen) must be notified. CERT-In must be notified within 6 hours. Generate the breach notification report and contact affected individuals.",
                "linux_cmd": "# Generate DPDP breach notification:\ncurl -X POST http://localhost:8000/reports/<CASE_ID> \\\n  -H 'Authorization: Bearer <TOKEN>' \\\n  --output DPDP_Exfiltration_Report.pdf\n\n# Email CERT-In:\n# To: incident@cert-in.org.in\n# Subject: Data Breach Notification — [Organisation] — [Date]\n# Attach: DPDP_Exfiltration_Report.pdf",
                "windows_cmd": "# Same API call from PowerShell:\nInvoke-WebRequest -Uri 'http://localhost:8000/reports/<CASE_ID>' \\\n  -Headers @{Authorization='Bearer <TOKEN>'} -Method POST \\\n  -OutFile DPDP_Exfiltration_Report.pdf",
                "goal": "Meet DPDP Act 2023 mandatory notification requirements",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Implement DLP controls",
                "description": "After the incident is contained, implement Data Loss Prevention controls to monitor and block unauthorised data transfers in future.",
                "linux_cmd": "# Monitor outbound data with OpenDLP or similar:\n# Configure network monitoring on the gateway:\nsudo apt install nload iftop nethogs -y\n\n# Set up egress filtering rules:\n# Only allow outbound on specific ports and destinations\nsudo ufw default deny outgoing\nsudo ufw allow out 80/tcp\nsudo ufw allow out 443/tcp\nsudo ufw allow out 53/udp\n\n# Log all outbound connections:\nsudo ufw logging on",
                "windows_cmd": "# Enable Windows Information Protection:\n# Configure via Intune or Group Policy\n\n# Monitor outbound with Windows Firewall logging:\nnetsh advfirewall set global statefulftp disable\nnetsh advfirewall set currentprofile logging filename C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log",
                "goal": "Prevent future exfiltration with ongoing monitoring",
                "is_blocking": False
            }
        ]
    },

    # ─── 5. INSIDER ───────────────────────────────────────────────────────────
    {
        "attack_type": "insider",
        "name": "Insider Threat Response Playbook",
        "description": "Response for suspected insider threats — employees or contractors misusing access. Requires careful handling to avoid tipping off the suspect while preserving evidence for HR and legal proceedings.",
        "steps": [
            {
                "step_number": 1,
                "title": "Preserve evidence quietly — do not alert the suspect",
                "description": "Unlike external attacks, insider investigations require discretion. Preserve all evidence before taking any action that the suspect might notice. Contact HR and legal before doing anything visible to the employee.",
                "linux_cmd": "# Quietly capture logs without the user knowing:\n# Copy relevant auth logs to secure location:\nsudo cp /var/log/auth.log /secure-evidence/auth_$(date +%Y%m%d).log\n\n# Capture user's recent activity without logging in as them:\nsudo last username > /secure-evidence/login_history.txt\nsudo lastb username >> /secure-evidence/failed_logins.txt\n\n# Export user's process history (non-intrusively):\nsudo ausearch -ua $(id -u username) > /secure-evidence/audit_trail.txt",
                "windows_cmd": "# Export event logs for the user silently:\nGet-WinEvent -FilterHashtable @{LogName='Security'} | \\\n  Where-Object {$_.Message -like '*username*'} | \\\n  Export-Csv C:\\SecureEvidence\\user_events.csv -NoTypeInformation\n\n# Export file access logs:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} | \\\n  Where-Object {$_.Message -like '*username*'} | Select -First 100",
                "goal": "Gather evidence without alerting the suspect and allowing evidence destruction",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Establish the timeline of suspicious activity",
                "description": "Build a complete timeline of what the user accessed, when, from where, and what they did. This is the foundation of any HR or legal action.",
                "linux_cmd": "# Build access timeline:\ngrep 'username' /var/log/auth.log | grep -E 'Accepted|session opened|session closed' | \\\n  awk '{print $1, $2, $3, $NF}' | sort > /secure-evidence/timeline.txt\n\n# Check file access times (if audit logging is enabled):\nausearch -ua $(id -u username) -ts 2026-01-01 -te today | aureport --file\n\n# Check database access:\ngrep 'username' /var/log/postgresql/postgresql.log | grep -E 'SELECT|INSERT|DELETE|UPDATE' | \\\n  grep -v 'pg_' > /secure-evidence/db_queries.txt\n\n# Check VPN/remote access logs:\ngrep 'username' /var/log/openvpn.log",
                "windows_cmd": "# Build Windows timeline:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4624,4634,4663,4688} | \\\n  Where-Object {$_.Message -like '*username*'} | \\\n  Sort-Object TimeCreated | Export-Csv timeline.csv",
                "goal": "Create a legally admissible activity timeline",
                "is_blocking": False
            },
            {
                "step_number": 3,
                "title": "Identify what data was accessed or copied",
                "description": "Determine exactly what sensitive data the insider accessed, modified, or copied. Pay special attention to bulk downloads, data exports, and access to data outside their normal role.",
                "linux_cmd": "# Check files accessed outside normal work hours:\nausearch -ua $(id -u username) -ts 2026-01-01T00:00:00 -te 2026-01-01T07:00:00 | \\\n  aureport --file | grep 'read\\|open'\n\n# Check for large file copies or downloads:\nfind /home/username /tmp -type f -newer /tmp/reference_date -size +10M -ls\n\n# Check email sent (if sendmail/postfix logs are available):\ngrep 'username@domain' /var/log/mail.log | grep 'status=sent'\n\n# Check USB device usage:\ngrep -i 'usb\\|removable' /var/log/syslog | tail -50",
                "windows_cmd": "# Check file access for the user:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} | \\\n  Where-Object {$_.Message -like '*username*' -and $_.Message -like '*sensitive*'} | Select -First 50\n\n# Check for USB device connections:\nGet-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-DriverFrameworks-UserMode/Operational'; Id=2003} | Select -First 10",
                "goal": "Establish what data was compromised and determine DPDP notification obligation",
                "is_blocking": False
            },
            {
                "step_number": 4,
                "title": "Involve HR and legal before taking action",
                "description": "Do NOT suspend the account, confront the employee, or take disciplinary action without HR and legal approval. Premature action can compromise legal proceedings and expose the organisation to wrongful termination claims.",
                "linux_cmd": "# Document your findings clearly:\ncat > /secure-evidence/summary_for_hr.txt << EOF\nDate of discovery: $(date)\nEmployee: [name]\nSuspicious activity: [describe]\nTime period: [start] to [end]\nData potentially accessed: [list]\nEvidence location: /secure-evidence/\nEOF\n\n# Do not take any system action until HR/legal approve\necho 'WAITING FOR HR AND LEGAL APPROVAL BEFORE PROCEEDING'",
                "windows_cmd": "# Same — document findings and wait for HR/legal\n# Do not lock the account yet\n# Do not confront the employee",
                "goal": "Ensure legally sound process that protects the organisation",
                "is_blocking": True
            },
            {
                "step_number": 5,
                "title": "Revoke access and contain (after HR approval)",
                "description": "Only after HR and legal have reviewed the evidence and approved action: disable the account, revoke all access credentials, and collect the employee's devices.",
                "linux_cmd": "# Disable user account (after HR approval):\nsudo usermod -L username   # Lock account\nsudo usermod -s /usr/sbin/nologin username   # Disable shell\n\n# Revoke SSH keys:\nsudo mv /home/username/.ssh/authorized_keys /secure-evidence/revoked_keys_username\n\n# Remove from sudo group:\nsudo gpasswd -d username sudo\n\n# Expire all active sessions:\nsudo pkill -u username\n\n# Change shared passwords the user knew:\n# (document which shared passwords need rotation)",
                "windows_cmd": "# Disable AD account (after HR approval):\nDisable-ADAccount -Identity 'username'\n\n# Reset password immediately:\nSet-ADAccountPassword -Identity 'username' -Reset -NewPassword (ConvertTo-SecureString 'TempPass@123!' -AsPlainText -Force)\n\n# Revoke all active sessions:\nRevoke-MgUserSignInSession -UserId 'user@domain.com'",
                "goal": "Remove access without tipping off prematurely",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Review and tighten access controls",
                "description": "After the incident, conduct a least-privilege audit. Employees should only have access to data required for their specific role. Remove accumulated permissions that were granted over time but are no longer needed.",
                "linux_cmd": "# Audit all users with elevated permissions:\nsudo grep -E '^sudo:|^admin:' /etc/group\ncat /etc/sudoers\n\n# List all users who can SSH to this server:\ncat /etc/ssh/sshd_config | grep 'AllowUsers\\|AllowGroups'\n\n# Review all files accessible to user's group:\nfind / -group groupname -type f 2>/dev/null | head -50\n\n# Implement mandatory access control (AppArmor/SELinux):\nsudo apt install apparmor-utils\nsudo aa-status",
                "windows_cmd": "# Audit all users in privileged groups:\nGet-ADGroupMember -Identity 'Domain Admins' | Select Name, SamAccountName\nGet-ADGroupMember -Identity 'Administrators' | Select Name\n\n# Review user permissions on sensitive folders:\nGet-Acl 'C:\\SensitiveData' | Format-List",
                "goal": "Implement least-privilege to reduce insider threat exposure",
                "is_blocking": False
            }
        ]
    }
]


def seed_playbooks():
    db = SessionLocal()
    try:
        # Clear existing playbooks
        db.query(PlaybookStep).delete()
        db.query(Playbook).delete()
        db.commit()
        print("Cleared existing playbooks.")

        total_steps = 0
        for pb_data in PLAYBOOKS:
            steps_data = pb_data.pop("steps")

            playbook = Playbook(
                attack_type=pb_data["attack_type"],
                name=pb_data["name"],
                description=pb_data["description"]
            )
            db.add(playbook)
            db.flush()   # Get the playbook ID

            for step_data in steps_data:
                step = PlaybookStep(playbook_id=playbook.id, **step_data)
                db.add(step)
                total_steps += 1

            print(f"  ✓ {playbook.name} ({len(steps_data)} steps)")

        db.commit()
        print(f"\nSeeded {len(PLAYBOOKS)} playbooks with {total_steps} steps total.")
        print("\nVerify with:")
        print("  curl http://localhost:8000/playbooks -H 'Authorization: Bearer <TOKEN>'")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_playbooks()
```

Run it:
```bash
cd backend
source venv/bin/activate
python scripts/seed_playbooks.py
```

Expected output:
```
Cleared existing playbooks.
  ✓ Ransomware Response Playbook (7 steps)
  ✓ Phishing Attack Response Playbook (6 steps)
  ✓ Unauthorised Access Response Playbook (6 steps)
  ✓ Data Exfiltration Response Playbook (6 steps)
  ✓ Insider Threat Response Playbook (6 steps)

Seeded 5 playbooks with 31 steps total.
```

Commit:
```bash
git add backend/scripts/seed_playbooks.py
git commit -m "feat: seed 5 production playbooks with 31 steps — real Linux commands and DPDP guidance"
```

---

## Day 4 — Playbook Runner Frontend

### Task 4.1 — Add playbook API calls to client.ts

```typescript
// Add to frontend/src/api/client.ts

// ─── Playbooks ────────────────────────────────────────────────────────────────

export const getPlaybooks = async () => {
  const { data } = await api.get("/playbooks");
  return data;
};

export const getPlaybook = async (attackType: string) => {
  const { data } = await api.get(`/playbooks/${attackType}`);
  return data;
};

export const getCasePlaybook = async (caseId: string) => {
  const { data } = await api.get(`/cases/${caseId}/playbook`);
  return data;
};

export const completeStep = async (caseId: string, stepId: number) => {
  const { data } = await api.post(`/cases/${caseId}/steps/${stepId}/complete`);
  return data;
};

// ─── Org ─────────────────────────────────────────────────────────────────────

export const getOrg = async () => {
  const { data } = await api.get("/org");
  return data;
};

export const updateOrg = async (payload: {
  name?: string;
  dpo_name?: string;
  dpo_email?: string;
  address?: string;
  cert_in_email?: string;
}) => {
  const { data } = await api.put("/org", payload);
  return data;
};
```

---

### Task 4.2 — Add playbook types to types/index.ts

```typescript
// Add to frontend/src/types/index.ts

export interface PlaybookStep {
  id: number;
  step_number: number;
  title: string;
  description: string;
  linux_cmd: string | null;
  windows_cmd: string | null;
  goal: string | null;
  is_blocking: boolean;
}

export interface Playbook {
  id: number;
  attack_type: string;
  name: string;
  description: string | null;
  steps: PlaybookStep[];
}

export interface PlaybookListItem {
  id: number;
  attack_type: string;
  name: string;
  description: string | null;
}
```

---

### Task 4.3 — Create PlaybookRunner component

Create `frontend/src/components/playbook/PlaybookRunner.tsx`:

```tsx
// src/components/playbook/PlaybookRunner.tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { completeStep } from "../../api/client";
import type { Playbook, PlaybookStep } from "../../types";
import {
  CheckCircle2, Circle, ChevronDown, ChevronUp,
  Terminal, Target, AlertTriangle
} from "lucide-react";
import { clsx } from "clsx";

interface Props {
  playbook: Playbook;
  caseId: string;
  completedStepIds?: number[];  // IDs of steps already completed for this case
}

export default function PlaybookRunner({ playbook, caseId, completedStepIds = [] }: Props) {
  const queryClient = useQueryClient();
  const [expandedStep, setExpandedStep] = useState<number | null>(playbook.steps[0]?.id ?? null);
  const [localCompleted, setLocalCompleted] = useState<Set<number>>(new Set(completedStepIds));
  const [activeTab, setActiveTab] = useState<"linux" | "windows">("linux");

  const completeMutation = useMutation({
    mutationFn: ({ stepId }: { stepId: number }) => completeStep(caseId, stepId),
    onSuccess: (_, { stepId }) => {
      setLocalCompleted(prev => new Set([...prev, stepId]));
      queryClient.invalidateQueries({ queryKey: ["case", caseId] });
    },
  });

  const completedCount = localCompleted.size;
  const totalSteps = playbook.steps.length;
  const progressPct = totalSteps > 0 ? (completedCount / totalSteps) * 100 : 0;

  return (
    <div className="space-y-4">

      {/* Header + Progress */}
      <div className="bg-surface-800 rounded-xl border border-surface-700 p-5">
        <h3 className="text-sm font-semibold text-white mb-1">{playbook.name}</h3>
        {playbook.description && (
          <p className="text-xs text-slate-400 mb-4">{playbook.description}</p>
        )}

        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-surface-600 rounded-full overflow-hidden">
            <div
              className="h-2 rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-xs text-slate-400 shrink-0">
            {completedCount} / {totalSteps} steps
          </span>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {playbook.steps.map((step, idx) => {
          const isCompleted = localCompleted.has(step.id);
          const isExpanded  = expandedStep === step.id;
          const isBlocking  = step.is_blocking && !isCompleted && idx > 0 &&
                              !localCompleted.has(playbook.steps[idx - 1]?.id ?? -1);

          return (
            <div
              key={step.id}
              className={clsx(
                "bg-surface-800 border rounded-xl overflow-hidden transition-colors",
                isCompleted ? "border-green-500/30" : "border-surface-700"
              )}
            >
              {/* Step header */}
              <button
                onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-700 transition-colors"
              >
                {/* Complete/pending icon */}
                {isCompleted ? (
                  <CheckCircle2 size={18} className="text-green-400 shrink-0" />
                ) : (
                  <Circle size={18} className="text-slate-600 shrink-0" />
                )}

                {/* Step number + title */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500 font-mono">
                      Step {step.step_number}
                    </span>
                    {step.is_blocking && (
                      <span className="text-xs text-red-400 font-medium">REQUIRED</span>
                    )}
                  </div>
                  <p className={clsx(
                    "text-sm font-medium mt-0.5",
                    isCompleted ? "text-slate-400 line-through" : "text-slate-200"
                  )}>
                    {step.title}
                  </p>
                </div>

                {/* Expand toggle */}
                {isExpanded
                  ? <ChevronUp size={14} className="text-slate-500 shrink-0" />
                  : <ChevronDown size={14} className="text-slate-500 shrink-0" />
                }
              </button>

              {/* Step detail (expanded) */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-4 border-t border-surface-700 pt-4">

                  {/* Description */}
                  <p className="text-sm text-slate-300 leading-relaxed">
                    {step.description}
                  </p>

                  {/* Goal */}
                  {step.goal && (
                    <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
                      <Target size={14} className="text-blue-400 shrink-0 mt-0.5" />
                      <p className="text-xs text-blue-300">
                        <span className="font-semibold">Goal: </span>
                        {step.goal}
                      </p>
                    </div>
                  )}

                  {/* Commands */}
                  {(step.linux_cmd || step.windows_cmd) && (
                    <div>
                      {/* OS tab switcher */}
                      <div className="flex gap-1 mb-2">
                        {step.linux_cmd && (
                          <button
                            onClick={() => setActiveTab("linux")}
                            className={clsx(
                              "text-xs px-3 py-1 rounded-md transition-colors",
                              activeTab === "linux"
                                ? "bg-surface-600 text-slate-200"
                                : "text-slate-500 hover:text-slate-300"
                            )}
                          >
                            Linux
                          </button>
                        )}
                        {step.windows_cmd && (
                          <button
                            onClick={() => setActiveTab("windows")}
                            className={clsx(
                              "text-xs px-3 py-1 rounded-md transition-colors",
                              activeTab === "windows"
                                ? "bg-surface-600 text-slate-200"
                                : "text-slate-500 hover:text-slate-300"
                            )}
                          >
                            Windows
                          </button>
                        )}
                      </div>

                      {/* Command block */}
                      <div className="bg-slate-900 border border-surface-600 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Terminal size={12} className="text-slate-500" />
                          <span className="text-xs text-slate-500">
                            {activeTab === "linux" ? "Bash" : "PowerShell"}
                          </span>
                        </div>
                        <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap overflow-x-auto">
                          {activeTab === "linux" ? step.linux_cmd : step.windows_cmd}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Complete button */}
                  {!isCompleted && (
                    <button
                      onClick={() => completeMutation.mutate({ stepId: step.id })}
                      disabled={completeMutation.isPending}
                      className="flex items-center gap-2 px-4 py-2 text-xs
                                 bg-green-600 hover:bg-green-700 text-white rounded-lg
                                 transition-colors disabled:opacity-50"
                    >
                      <CheckCircle2 size={13} />
                      {completeMutation.isPending ? "Marking complete..." : "Mark as Complete"}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

---

### Task 4.4 — Create PlaybookPage

Create `frontend/src/pages/PlaybookPage.tsx`:

```tsx
// src/pages/PlaybookPage.tsx
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCase, getCasePlaybook } from "../api/client";
import PlaybookRunner from "../components/playbook/PlaybookRunner";
import { ArrowLeft, BookOpen } from "lucide-react";

export default function PlaybookPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: caseData } = useQuery({
    queryKey: ["case", id],
    queryFn: () => getCase(id!),
    enabled: !!id,
  });

  const { data: playbook, isLoading, isError } = useQuery({
    queryKey: ["playbook", id],
    queryFn: () => getCasePlaybook(id!),
    enabled: !!id,
  });

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(`/cases/${id}`)}
          className="flex items-center gap-2 text-sm text-slate-400
                     hover:text-slate-200 transition-colors"
        >
          <ArrowLeft size={14} />
          Back to Case
        </button>
        {caseData && (
          <div>
            <div className="flex items-center gap-2">
              <BookOpen size={14} className="text-blue-400" />
              <span className="text-sm font-medium text-white">Response Playbook</span>
            </div>
            <p className="text-xs text-slate-500 font-mono">{caseData.id}</p>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="text-center text-slate-500 py-16">Loading playbook...</div>
      )}
      {isError && (
        <div className="text-center text-slate-500 py-16">
          No playbook found for this breach type.
        </div>
      )}
      {playbook && caseData && (
        <PlaybookRunner
          playbook={playbook}
          caseId={id!}
          completedStepIds={[]}
        />
      )}
    </div>
  );
}
```

---

### Task 4.5 — Add playbook route to App.tsx and link from CaseDetail

Add route in `frontend/src/App.tsx`:
```tsx
import PlaybookPage from "./pages/PlaybookPage";

// Inside AppLayout routes:
<Route path="/cases/:id/playbook" element={<PlaybookPage />} />
```

Add a "Run Playbook" button in `CaseDetail.tsx` header section:
```tsx
import { BookOpen } from "lucide-react";
import { useNavigate } from "react-router-dom";

// Inside CaseDetail component:
const navigate = useNavigate();

// Add this button next to Re-run AI and DPDP Report:
<button
  onClick={() => navigate(`/cases/${c.id}/playbook`)}
  className="flex items-center gap-2 px-3 py-1.5 text-xs
             bg-green-600 hover:bg-green-700 text-white rounded-lg
             transition-colors"
>
  <BookOpen size={12} />
  Run Playbook
</button>
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: playbook runner — step-by-step checklist with Linux/Windows commands and complete tracking"
```

---

## Day 5 — Docker Compose Full Stack

### Task 5.1 — Create backend/Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

# Install system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for reports and evidence
RUN mkdir -p /data/reports /data/evidence

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Task 5.2 — Create frontend/Dockerfile

```dockerfile
# frontend/Dockerfile

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .

# Build for production
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

---

### Task 5.3 — Create frontend/nginx.conf

```nginx
# frontend/nginx.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # React Router — serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to FastAPI backend
    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }

    # Cache static assets
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
```

---

### Task 5.4 — Create docker-compose.yml at project root

```yaml
# docker-compose.yml
version: "3.9"

services:

  # ─── PostgreSQL Database ─────────────────────────────────────────────────
  postgres:
    image: postgres:15-alpine
    container_name: zr-postgres
    environment:
      POSTGRES_DB:       zerorespondnd
      POSTGRES_USER:     zr
      POSTGRES_PASSWORD: secret
    volumes:
      - zr_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U zr -d zerorespondnd"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - zr-network

  # ─── FastAPI Backend ─────────────────────────────────────────────────────
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: zr-backend
    environment:
      DATABASE_URL: postgresql://zr:secret@postgres:5432/zerorespondnd
      OLLAMA_URL:   http://host.docker.internal:11434   # Ollama runs on host
      OLLAMA_MODEL: qwen2.5:7b
      SECRET_KEY:   change-this-to-a-secure-random-string-in-production
      ENVIRONMENT:  production
    volumes:
      - ./data/reports:/data/reports         # DPDP PDFs
      - ./data/evidence:/data/evidence       # Evidence uploads
      - ./backend/templates:/app/templates   # Jinja2 templates
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - zr-network
    restart: unless-stopped

  # ─── React Frontend + Nginx ───────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: zr-frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - zr-network
    restart: unless-stopped

# ─── Volumes ──────────────────────────────────────────────────────────────────
volumes:
  zr_pgdata:
    name: zr_pgdata

# ─── Networks ─────────────────────────────────────────────────────────────────
networks:
  zr-network:
    name: zr-network
    driver: bridge
```

---

### Task 5.5 — Create a .env.production for Docker

Create `backend/.env.production`:
```env
DATABASE_URL=postgresql://zr:secret@postgres:5432/zerorespondnd
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:7b
SECRET_KEY=generate-with-openssl-rand-hex-32-and-keep-secret
ENVIRONMENT=production
```

> **Important:** Generate a real SECRET_KEY before deploying:
```bash
openssl rand -hex 32
# Copy the output and put it in .env.production
```

---

### Task 5.6 — Add Alembic run-on-startup script

The backend container needs to run migrations on startup before accepting requests. Create `backend/start.sh`:

```bash
#!/bin/bash
# backend/start.sh
set -e

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Update `backend/Dockerfile` CMD:
```dockerfile
# Replace the last CMD line with:
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]
```

Commit:
```bash
git add backend/Dockerfile frontend/Dockerfile frontend/nginx.conf \
        docker-compose.yml backend/start.sh backend/.env.production
git commit -m "feat: Docker Compose full stack — postgres + fastapi + react + nginx"
```

---

## Day 6 — Org Profile Settings Page (Frontend)

### Task 6.1 — Create Settings page

Create `frontend/src/pages/Settings.tsx`:

```tsx
// src/pages/Settings.tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getOrg, updateOrg } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Building2, Save, CheckCircle2 } from "lucide-react";

export default function Settings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";

  const { data: org, isLoading } = useQuery({
    queryKey: ["org"],
    queryFn: getOrg,
  });

  const [form, setForm] = useState({
    name:          org?.name ?? "",
    dpo_name:      org?.dpo_name ?? "",
    dpo_email:     org?.dpo_email ?? "",
    address:       org?.address ?? "",
    cert_in_email: org?.cert_in_email ?? "",
  });

  // Sync form when org data loads
  if (org && !form.name && !isLoading) {
    setForm({
      name:          org.name,
      dpo_name:      org.dpo_name,
      dpo_email:     org.dpo_email,
      address:       org.address ?? "",
      cert_in_email: org.cert_in_email,
    });
  }

  const mutation = useMutation({
    mutationFn: () => updateOrg(form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["org"] }),
  });

  if (isLoading) {
    return <div className="text-center text-slate-500 py-16">Loading settings...</div>;
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Building2 size={18} className="text-blue-400" />
          <h2 className="text-xl font-semibold text-white">Organisation Settings</h2>
        </div>
        <p className="text-sm text-slate-400">
          This information appears on all DPDP Act 2023 breach notification PDFs.
          {!isAdmin && " Only admins can update these settings."}
        </p>
      </div>

      <div className="bg-surface-800 rounded-xl border border-surface-700 p-6 space-y-4">
        {[
          { label: "Organisation Name",       key: "name",          placeholder: "Coimbatore Medical College Hospital" },
          { label: "Data Protection Officer", key: "dpo_name",      placeholder: "Dr. Full Name" },
          { label: "DPO Email",               key: "dpo_email",     placeholder: "dpo@organisation.in" },
          { label: "Organisation Address",    key: "address",       placeholder: "City, State, PIN Code" },
          { label: "CERT-In Notification Email", key: "cert_in_email", placeholder: "incident@cert-in.org.in" },
        ].map(({ label, key, placeholder }) => (
          <div key={key}>
            <label className="text-xs text-slate-400 mb-1 block">{label}</label>
            <input
              type="text"
              value={form[key as keyof typeof form]}
              onChange={(e) => setForm(prev => ({ ...prev, [key]: e.target.value }))}
              placeholder={placeholder}
              disabled={!isAdmin}
              className="w-full bg-surface-700 border border-surface-600 text-slate-200
                         text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500
                         disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        ))}

        {isAdmin && (
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="flex items-center gap-2 px-4 py-2 text-sm
                         bg-blue-600 hover:bg-blue-700 text-white rounded-lg
                         transition-colors disabled:opacity-50"
            >
              <Save size={14} />
              {mutation.isPending ? "Saving..." : "Save Settings"}
            </button>
            {mutation.isSuccess && (
              <div className="flex items-center gap-1 text-xs text-green-400">
                <CheckCircle2 size={13} />
                Saved
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

---

### Task 6.2 — Add Settings to Sidebar and App router

Update `frontend/src/components/layout/Sidebar.tsx`:
```tsx
import { LayoutDashboard, FolderOpen, Bell, Shield, Settings } from "lucide-react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/cases",     icon: FolderOpen,      label: "Cases"     },
  { to: "/alerts",    icon: Bell,            label: "Alerts"    },
  { to: "/settings",  icon: Settings,        label: "Settings"  },
];
```

Add route in `App.tsx`:
```tsx
import Settings from "./pages/Settings";

// Inside AppLayout routes:
<Route path="/settings" element={<Settings />} />
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: settings page for org profile — DPDP report data management"
```

---

## Day 7 — Final Verification + Week 6 Completion Check

### Task 7.1 — Test Docker Compose deployment

```bash
# Build and start everything
docker compose up --build -d

# Watch startup logs
docker compose logs -f

# Expected sequence:
# zr-postgres: database system is ready to accept connections
# zr-backend:  Running Alembic migrations...
# zr-backend:  Application startup complete.
# zr-frontend: nginx started
```

Open http://localhost in your browser — should redirect to `/login`.

---

### Task 7.2 — Run the full completion checklist

```bash
# Start the API for curl tests (can use Docker or dev server)
BASE="http://localhost:8000"

# First login to get token
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hospital.in","password":"SecurePass123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Check 1: Org profile GET and PUT
curl -s -X PUT $BASE/org \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"Test Hospital","dpo_name":"Dr. Test","dpo_email":"dpo@test.in","cert_in_email":"incident@cert-in.org.in"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['name']=='Test Hospital'; print('✓ PUT /org works')"

curl -s $BASE/org -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['dpo_name']=='Dr. Test'; print('✓ GET /org returns updated profile')"

# Check 2: Playbooks seeded correctly
COUNT=$(curl -s $BASE/playbooks -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$COUNT" = "5" ] && echo "✓ 5 playbooks seeded" || echo "✗ Expected 5, got $COUNT"

# Check 3: Each playbook has steps
for TYPE in ransomware phishing unauthorized_access exfiltration insider; do
  STEPS=$(curl -s "$BASE/playbooks/$TYPE" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['steps']))")
  echo "✓ $TYPE playbook: $STEPS steps"
done

# Check 4: Case playbook endpoint
curl -s "$BASE/cases/IR-20260623-0003/playbook" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['attack_type']=='ransomware'; print('✓ Case playbook returns correct playbook for breach type')"

# Check 5: Complete a step
STEP_ID=$(curl -s "$BASE/playbooks/ransomware" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['steps'][0]['id'])")

curl -s -X POST "$BASE/cases/IR-20260623-0003/steps/$STEP_ID/complete" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['completed_at'] is not None; print('✓ Step completion works')"

# Check 6: Idempotent step completion (second call returns same record)
curl -s -X POST "$BASE/cases/IR-20260623-0003/steps/$STEP_ID/complete" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['playbook_step_id'] == $STEP_ID; print('✓ Step completion is idempotent')"

# Check 7: Docker Compose stack starts cleanly
docker compose ps
echo "✓ All containers running — check manually"
```

---

### Task 7.3 — Manual UI checks

```
✓ http://localhost loads and redirects to /login
✓ Login with admin credentials works via Docker stack
✓ Sidebar shows Settings link
✓ Settings page loads org profile data
✓ Updating org name saves and persists
✓ Analyst user sees Settings as read-only (inputs disabled)
✓ Case detail page shows "Run Playbook" button
✓ Clicking "Run Playbook" navigates to /cases/{id}/playbook
✓ Playbook steps are shown in order with descriptions
✓ Linux/Windows tab switcher works on steps with commands
✓ "Mark as Complete" button marks step as done with green tick
✓ Progress bar updates when steps are completed
✓ DPDP Report PDF now shows real org name and DPO details
```

---

### Task 7.4 — Final commit and tag

```bash
git add .
git commit -m "feat: week 6 complete — org profile API, playbooks, playbook runner, Docker Compose"
git tag v0.6.0-week6
git push origin main --tags
```

---

## Week 6 Summary

| Day | What you built | Verification |
|-----|----------------|-------------|
| 1 | `GET /org`, `PUT /org` (admin only) — org profile API on top of existing model | PUT updates persist, appear in DPDP PDFs, analyst blocked with 403 |
| 2 | Playbooks router — list all, get by attack type, get for case, complete step (idempotent) | All 5 attack types return playbooks, step completion records saved |
| 3 | Seed script with 5 production playbooks, 31 steps, real Linux + Windows commands | `python scripts/seed_playbooks.py` seeds all playbooks correctly |
| 4 | `PlaybookRunner` component with progress bar, step expand/collapse, OS tab switcher, complete button. `PlaybookPage` and route | Run Playbook flow works end to end from case detail |
| 5 | `backend/Dockerfile`, `frontend/Dockerfile`, `nginx.conf`, `docker-compose.yml`, `start.sh` | `docker compose up --build` starts full stack on port 80 |
| 6 | Settings page for org profile management — admin editable, analyst read-only | Form saves, data appears in next DPDP PDF |
| 7 | 7-check automated checklist + 13 manual UI checks | All checks pass |

**You are now ready for Week 7 — Evidence Management + Wazuh Integration.**

---

*ZeroRespond · Manikandan · KCT 2023–2027*
