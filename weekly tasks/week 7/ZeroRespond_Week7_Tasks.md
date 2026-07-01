# ZeroRespond — Week 7 Task List
**Phase 7 · Evidence Management + Wazuh Integration**

> **Goal by end of Week 7:** Responders can upload evidence files (screenshots, log exports, pcap files) to a case and they are securely stored on disk with metadata in the database. Separately, a real Wazuh manager sends alerts to ZeroRespond automatically via a log-tailing alert-processor — no more manual curl commands. By the end of this week, your alert pipeline goes from "I manually POST alerts for testing" to "Wazuh detects something and ZeroRespond responds within seconds, completely on its own."

---

## What you have coming in from Week 6

- `Evidence` model already exists in `backend/app/models/evidence.py` (from Week 1)
- `data/evidence/` directory exists and is gitignored
- JWT auth protecting all routes
- `POST /alerts` — alert ingestion with async AI enrichment via Ollama
- Org profile, playbooks, Docker Compose — all working
- Frontend: Dashboard, Cases, Case Detail (with Run Playbook + DPDP Report buttons), Alerts, Settings

---

## Week 7 Architecture

```
What you are building:

Backend:
  POST   /cases/{id}/evidence     ← upload a file, attach to case
  GET    /cases/{id}/evidence     ← list evidence for a case
  GET    /evidence/{id}/download  ← download a specific evidence file
  DELETE /evidence/{id}           ← delete evidence (admin only)

  New files:
  backend/app/
  ├── schemas/
  │   └── evidence.py            ← EvidenceOut schema
  ├── routers/
  │   └── evidence.py            ← upload, list, download, delete
  └── services/
      └── evidence_service.py    ← file storage, size limits, type validation

  alert-processor/                ← NEW standalone service
  ├── wazuh_listener.py           ← tails Wazuh alerts.json, forwards to FastAPI
  ├── requirements.txt
  └── Dockerfile

Frontend:
  New/updated files:
  frontend/src/
  ├── components/
  │   └── evidence/
  │       └── EvidenceUpload.tsx  ← drag-drop upload + file list
  └── api/
      └── client.ts                ← add uploadEvidence(), getEvidence(), deleteEvidenceFile()
```

---

## Why a separate alert-processor service?

Wazuh's built-in integration framework is limited and does not give you retries, backoff, or custom payload shaping out of the box. A small standalone Python service sitting between Wazuh and FastAPI gives you:
- A buffer if FastAPI is temporarily restarting
- A single place to transform Wazuh's alert JSON shape into your `AlertCreate` schema shape
- Retry logic with exponential backoff so no alert is silently dropped
- Isolation — if Wazuh's log format changes, you only edit one small file

This mirrors exactly the **L1 → L2 → L3** flow in your architecture diagram.

---

## Day 1 — Evidence Schema + Service

### Task 1.1 — Review the Evidence model (already exists)

Your `backend/app/models/evidence.py` from Week 1 already has everything needed:

```python
class Evidence(Base):
    __tablename__ = "evidence"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    case_id     = Column(String(30), ForeignKey("cases.id"), nullable=False)
    filename    = Column(String(255), nullable=False)
    filepath    = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    file_size   = Column(Integer, nullable=True)
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    case        = relationship("Case", back_populates="evidence")
```

No migration needed this week — the table already exists from Week 1's initial schema.

---

### Task 1.2 — Create backend/app/schemas/evidence.py

```python
# backend/app/schemas/evidence.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EvidenceOut(BaseModel):
    """Returned by GET /cases/{id}/evidence and POST /cases/{id}/evidence."""
    id:          int
    case_id:     str
    filename:    str
    description: Optional[str]
    file_size:   Optional[int]
    uploaded_by: Optional[str]
    uploaded_at: datetime

    model_config = {"from_attributes": True}
```

> **Why no `filepath` in the schema?** Never expose the server's internal disk path to the frontend — that is an information disclosure risk. Downloads go through an endpoint, not a raw path.

---

### Task 1.3 — Create backend/app/services/evidence_service.py

```python
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
```

Commit:
```bash
git add backend/app/schemas/evidence.py backend/app/services/evidence_service.py
git commit -m "feat: evidence service — file upload validation, storage, deletion"
```

---

## Day 2 — Evidence Router

### Task 2.1 — Create backend/app/routers/evidence.py

```python
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
```

---

### Task 2.2 — Register both routers in main.py

```python
# backend/app/main.py
from app.routers import alerts, cases, auth, reports, org, playbooks, evidence  # ← add evidence

app.include_router(evidence.cases_evidence_router)
app.include_router(evidence.evidence_router)
```

---

### Task 2.3 — Test evidence upload manually

```bash
TOKEN="eyJ..."   # your admin token

echo "Suspicious login attempts logged at 2026-06-29 02:15 AM from 203.0.113.42" > /tmp/test_evidence.log

curl -X POST http://localhost:8000/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_evidence.log" \
  -F "description=Auth log excerpt showing brute force timestamps"
# Expected: 201 with evidence object including id, filename, file_size

curl http://localhost:8000/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN"
# Expected: array with 1 item

curl http://localhost:8000/evidence/1/download \
  -H "Authorization: Bearer $TOKEN" \
  --output /tmp/downloaded_evidence.log
diff /tmp/test_evidence.log /tmp/downloaded_evidence.log
# Expected: no output (files identical)

echo "malicious" > /tmp/test.exe
curl -X POST http://localhost:8000/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.exe"
# Expected: 400 "File type '.exe' not allowed..."

ANALYST_TOKEN="eyJ..."
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE http://localhost:8000/evidence/1 \
  -H "Authorization: Bearer $ANALYST_TOKEN")
[ "$RESP" = "403" ] && echo "✓ Analyst blocked from deleting evidence" || echo "✗ Expected 403, got $RESP"
```

Verify on disk:
```bash
find data/evidence -type f
# Expected: data/evidence/IR-20260623-0001/<uuid>_test_evidence.log
```

Commit:
```bash
git add backend/app/routers/evidence.py backend/app/main.py
git commit -m "feat: evidence router — upload, list, download, delete (admin-only delete)"
```

---

## Day 3 — Frontend Evidence Upload Component

### Task 3.1 — Add evidence types and API calls

Add to `frontend/src/types/index.ts`:

```typescript
export interface EvidenceItem {
  id: number;
  case_id: string;
  filename: string;
  description: string | null;
  file_size: number | null;
  uploaded_by: string | null;
  uploaded_at: string;
}
```

Add to `frontend/src/api/client.ts` (import `EvidenceItem` at the top):

```typescript
// ─── Evidence ────────────────────────────────────────────────────────────────

export const getEvidence = async (caseId: string): Promise<EvidenceItem[]> => {
  const { data } = await api.get(`/cases/${caseId}/evidence`);
  return data;
};

export const uploadEvidence = async (
  caseId: string,
  file: File,
  description?: string
): Promise<EvidenceItem> => {
  const formData = new FormData();
  formData.append("file", file);
  if (description) formData.append("description", description);

  const { data } = await api.post(`/cases/${caseId}/evidence`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
};

export const deleteEvidenceFile = async (evidenceId: number): Promise<void> => {
  await api.delete(`/evidence/${evidenceId}`);
};
```

---

### Task 3.2 — Create EvidenceUpload component

Create `frontend/src/components/evidence/EvidenceUpload.tsx`:

```tsx
// src/components/evidence/EvidenceUpload.tsx
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEvidence, uploadEvidence, deleteEvidenceFile } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import {
  Upload, FileText, Image as ImageIcon, FileArchive,
  Download, Trash2, Paperclip
} from "lucide-react";
import { formatDistanceToNow } from "../utils/time";

interface Props {
  caseId: string;
}

const TOKEN_KEY = "zr_access_token";

function fileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg"].includes(ext ?? "")) return ImageIcon;
  if (["zip", "pcap", "pcapng"].includes(ext ?? "")) return FileArchive;
  return FileText;
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function EvidenceUpload({ caseId }: Props) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [description, setDescription] = useState("");
  const [dragActive, setDragActive] = useState(false);

  const { data: evidenceList, isLoading } = useQuery({
    queryKey: ["evidence", caseId],
    queryFn: () => getEvidence(caseId),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, desc }: { file: File; desc: string }) =>
      uploadEvidence(caseId, file, desc),
    onSuccess: () => {
      setDescription("");
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (evidenceId: number) => deleteEvidenceFile(evidenceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] });
    },
  });

  const handleFileSelect = (file: File) => {
    uploadMutation.mutate({ file, desc: description });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDownload = (evidenceId: number, filename: string) => {
    const token = localStorage.getItem(TOKEN_KEY);
    fetch(`/api/evidence/${evidenceId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      });
  };

  const isAdmin = user?.role === "admin";

  return (
    <div className="bg-surface-800 rounded-xl border border-surface-700 p-6">
      <div className="flex items-center gap-2 mb-4">
        <Paperclip size={16} className="text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Evidence</h3>
        {evidenceList && (
          <span className="text-xs text-slate-500">({evidenceList.length})</span>
        )}
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
                   transition-colors mb-4 ${
          dragActive
            ? "border-blue-500 bg-blue-500/5"
            : "border-surface-600 hover:border-surface-500"
        }`}
      >
        <Upload size={20} className="mx-auto text-slate-500 mb-2" />
        <p className="text-sm text-slate-400">
          {uploadMutation.isPending ? "Uploading..." : "Drag and drop a file, or click to browse"}
        </p>
        <p className="text-xs text-slate-600 mt-1">
          Max 50MB · PNG, JPG, PDF, TXT, LOG, CSV, JSON, PCAP, ZIP, EVTX
        </p>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelect(file);
          }}
        />
      </div>

      <input
        type="text"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description for the next upload (optional)"
        className="w-full bg-surface-700 border border-surface-600 text-slate-200
                   text-sm rounded-lg px-3 py-2 mb-4 focus:outline-none focus:border-blue-500"
      />

      {uploadMutation.isError && (
        <p className="text-xs text-red-400 mb-3">
          Upload failed: {(uploadMutation.error as any)?.response?.data?.detail ?? "Unknown error"}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-slate-500">Loading evidence...</p>
      ) : !evidenceList || evidenceList.length === 0 ? (
        <p className="text-sm text-slate-500">No evidence uploaded yet.</p>
      ) : (
        <div className="space-y-2">
          {evidenceList.map((ev) => {
            const Icon = fileIcon(ev.filename);
            return (
              <div
                key={ev.id}
                className="flex items-center gap-3 bg-surface-700 rounded-lg p-3"
              >
                <Icon size={16} className="text-slate-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate">{ev.filename}</p>
                  {ev.description && (
                    <p className="text-xs text-slate-500 truncate">{ev.description}</p>
                  )}
                  <p className="text-xs text-slate-600 mt-0.5">
                    {formatBytes(ev.file_size)} · {ev.uploaded_by ?? "Unknown"} ·{" "}
                    {formatDistanceToNow(ev.uploaded_at)}
                  </p>
                </div>
                <button
                  onClick={() => handleDownload(ev.id, ev.filename)}
                  className="p-1.5 text-slate-400 hover:text-blue-400 transition-colors"
                  title="Download"
                >
                  <Download size={14} />
                </button>
                {isAdmin && (
                  <button
                    onClick={() => {
                      if (confirm(`Delete ${ev.filename}?`)) {
                        deleteMutation.mutate(ev.id);
                      }
                    }}
                    className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

---

### Task 3.3 — Add EvidenceUpload to the Case Detail page

Update `frontend/src/components/cases/CaseDetail.tsx`:

```tsx
// Add import at the top
import EvidenceUpload from "../evidence/EvidenceUpload";

// Add this section at the bottom of the returned JSX, after Responder Actions:
<EvidenceUpload caseId={c.id} />
```

Commit:
```bash
git add frontend/src/
git commit -m "feat: evidence upload UI — drag/drop, file list, download, admin delete"
```

---

## Day 4 — Wazuh Manager Setup (If Not Already Installed)

If you already have Wazuh running, skip to Task 4.4 and verify your setup matches.

---

### Task 4.1 — Install Wazuh manager (single-node, for development)

```bash
curl -sO https://packages.wazuh.com/4.7/wazuh-install.sh
sudo bash ./wazuh-install.sh -a
```

This installs Wazuh manager, indexer, and dashboard. Note the admin password printed at the end of installation — save it.

> **Production note:** for a real client deployment, Wazuh typically runs on a separate server from ZeroRespond, with Wazuh agents installed on every monitored endpoint. For Week 7 development, running everything on your dev machine is fine.

---

### Task 4.2 — Verify Wazuh is running

```bash
sudo systemctl status wazuh-manager
sudo systemctl status wazuh-indexer
sudo systemctl status wazuh-dashboard
```

Open the Wazuh dashboard and log in with the admin credentials from installation.

---

### Task 4.3 — Generate a test alert in Wazuh

```bash
for i in {1..6}; do
  sshpass -p "wrongpassword" ssh -o StrictHostKeyChecking=no fakeuser@localhost
done
```

Check Wazuh picked it up:
```bash
sudo tail -f /var/ossec/logs/alerts/alerts.json
```

You should see a JSON alert appear with `rule.level` around 10-12 and `rule.groups` containing `authentication_failed`.

---

### Task 4.4 — Understand the Wazuh alert JSON shape

A real Wazuh alert from `alerts.json` looks like this:

```json
{
  "timestamp": "2026-06-30T14:22:10.123+0530",
  "rule": {
    "level": 10,
    "description": "sshd: brute force trying to get access to the system.",
    "id": "5712",
    "groups": ["syslog", "sshd", "authentication_failures"]
  },
  "agent": {
    "id": "000",
    "name": "dev-machine"
  },
  "data": {
    "srcip": "127.0.0.1"
  },
  "id": "1719743530.193847",
  "location": "/var/log/auth.log"
}
```

Note the differences from your `AlertCreate` schema:
- `rule.id` is the Wazuh rule ID (you need `wazuh_rule_id`)
- `rule.level` maps to your `level`
- `rule.description` maps to your `description`
- `agent.name` maps to your `host`
- `data.srcip` maps to your `source_ip`
- `rule.groups` maps directly to your `groups`
- The whole alert is your `raw_json`

This mapping logic is exactly what the alert-processor service does.

---

## Day 5 — Alert Processor Service

This is a standalone Python service — not part of `backend/`. It tails Wazuh's alert log and forwards alerts to your FastAPI backend.

---

### Task 5.1 — Create the alert-processor folder structure

```bash
mkdir -p alert-processor
cd alert-processor
```

Create `alert-processor/requirements.txt`:
```
httpx==0.28.1
python-dotenv==1.2.2
```

Create `alert-processor/.env`:
```env
ZERORESPOND_API_URL=http://localhost:8000
ZERORESPOND_API_TOKEN=eyJ...
WAZUH_ALERTS_LOG=/var/ossec/logs/alerts/alerts.json
```

> **Why a static token here?** The alert-processor is a backend service, not a user. For a single-tenant on-prem deployment, a long-lived admin token (re-generated periodically) is acceptable for now.

---

### Task 5.2 — Create alert-processor/wazuh_listener.py

```python
#!/usr/bin/env python3
# alert-processor/wazuh_listener.py
"""
Tails the Wazuh alerts.json file and forwards new alerts to the ZeroRespond API.
Designed to run as a long-lived background process (systemd service or Docker container).
"""
import json
import time
import logging
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("wazuh-listener")

API_URL        = os.getenv("ZERORESPOND_API_URL", "http://localhost:8000")
API_TOKEN      = os.getenv("ZERORESPOND_API_TOKEN", "")
ALERTS_LOG     = Path(os.getenv("WAZUH_ALERTS_LOG", "/var/ossec/logs/alerts/alerts.json"))
MIN_ALERT_LEVEL = 5   # Ignore informational/noise alerts below this level


def map_wazuh_alert_to_zerorespond(wazuh_alert: dict) -> dict | None:
    """
    Transform a raw Wazuh alert JSON object into the shape ZeroRespond's
    AlertCreate schema expects.
    Returns None if the alert should be skipped (too low severity, malformed, etc.)
    """
    try:
        rule = wazuh_alert.get("rule", {})
        level = rule.get("level", 0)

        if level < MIN_ALERT_LEVEL:
            return None   # Skip noise

        agent = wazuh_alert.get("agent", {})
        data = wazuh_alert.get("data", {})

        return {
            "id": wazuh_alert.get("id"),
            "wazuh_rule_id": int(rule.get("id", 0)),
            "level": level,
            "description": rule.get("description", "No description")[:500],
            "source_ip": data.get("srcip"),
            "host": agent.get("name", "unknown-host"),
            "groups": rule.get("groups", []),
            "raw_json": wazuh_alert,
        }
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Failed to map Wazuh alert: {e} — alert: {wazuh_alert}")
        return None


def forward_alert(alert_payload: dict, max_retries: int = 3) -> bool:
    """
    POST the mapped alert to ZeroRespond's /alerts endpoint.
    Retries with exponential backoff. Returns True on success.
    409 (duplicate) is treated as success — it means the alert was already ingested.
    """
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = httpx.post(
                f"{API_URL}/alerts",
                json=alert_payload,
                headers=headers,
                timeout=10.0
            )
            if resp.status_code in (201, 409):
                logger.info(f"Forwarded alert {alert_payload['id']} (status {resp.status_code})")
                return True
            else:
                logger.warning(f"Unexpected status {resp.status_code} for alert {alert_payload['id']}: {resp.text}")
        except httpx.RequestError as e:
            logger.warning(f"Attempt {attempt}/{max_retries} failed for alert {alert_payload['id']}: {e}")

        if attempt < max_retries:
            time.sleep(2 ** attempt)   # 2s, 4s, 8s backoff

    logger.error(f"Giving up on alert {alert_payload['id']} after {max_retries} attempts")
    return False


def tail_alerts_log():
    """
    Continuously tail the Wazuh alerts.json file and forward new lines.
    Each line in alerts.json is one complete JSON object (JSON Lines format).
    """
    logger.info(f"Watching {ALERTS_LOG} for new alerts...")

    if not ALERTS_LOG.exists():
        logger.error(f"Alerts log not found at {ALERTS_LOG}. Is Wazuh installed and running?")
        return

    with open(ALERTS_LOG, "r") as f:
        f.seek(0, os.SEEK_END)   # Only process NEW alerts from now on

        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue

            line = line.strip()
            if not line:
                continue

            try:
                wazuh_alert = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(f"Skipping malformed JSON line: {line[:100]}")
                continue

            mapped = map_wazuh_alert_to_zerorespond(wazuh_alert)
            if mapped is None:
                continue

            forward_alert(mapped)


if __name__ == "__main__":
    if not API_TOKEN:
        logger.error("ZERORESPOND_API_TOKEN is not set. Edit alert-processor/.env")
        exit(1)
    tail_alerts_log()
```

---

### Task 5.3 — Test the alert processor manually

```bash
cd alert-processor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hospital.in","password":"SecurePass123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

sed -i "s/ZERORESPOND_API_TOKEN=.*/ZERORESPOND_API_TOKEN=$TOKEN/" .env

sudo -E python3 wazuh_listener.py
```

In another terminal, trigger a new alert:
```bash
for i in {1..6}; do
  sshpass -p "wrongpassword" ssh -o StrictHostKeyChecking=no fakeuser@localhost 2>/dev/null
done
```

You should see in the listener's terminal:
```
2026-06-30 14:25:10 [INFO] Forwarded alert 1719743610.293847 (status 201)
```

Verify in ZeroRespond:
```bash
curl http://localhost:8000/alerts -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -30
```

The new alert should appear, and within seconds a case should be created and AI-enriched.

Commit:
```bash
git add alert-processor/
git commit -m "feat: alert-processor service — tails Wazuh alerts.json, maps and forwards to ZeroRespond API"
```

> **Note:** do not commit `alert-processor/.env` — add it to `.gitignore` if not already covered.

---

## Day 6 — Dockerize Alert Processor + systemd Alternative

### Task 6.1 — Create alert-processor/Dockerfile

```dockerfile
# alert-processor/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wazuh_listener.py .

CMD ["python3", "wazuh_listener.py"]
```

---

### Task 6.2 — Add alert-processor to docker-compose.yml

```yaml
# Add this service to docker-compose.yml

  alert-processor:
    build:
      context: ./alert-processor
      dockerfile: Dockerfile
    container_name: zr-alert-processor
    environment:
      ZERORESPOND_API_URL: http://backend:8000
      ZERORESPOND_API_TOKEN: ${ZERORESPOND_API_TOKEN}
      WAZUH_ALERTS_LOG: /wazuh-logs/alerts.json
    volumes:
      - /var/ossec/logs/alerts:/wazuh-logs:ro
    depends_on:
      - backend
    networks:
      - zr-network
    restart: unless-stopped
```

> **Important:** this assumes Wazuh runs on the same host as Docker Compose, with its logs accessible at `/var/ossec/logs/alerts`. If Wazuh runs on a separate server, configure Wazuh's HTTP integration to POST directly to a small webhook receiver instead — a later hardening task for specific client network topologies.

---

### Task 6.3 — Alternative: systemd service (non-Docker deployments)

Create `alert-processor/zerorespond-listener.service`:
```ini
[Unit]
Description=ZeroRespond Wazuh Alert Listener
After=network.target wazuh-manager.service

[Service]
Type=simple
User=zerorespond
WorkingDirectory=/opt/zerorespond/alert-processor
EnvironmentFile=/opt/zerorespond/alert-processor/.env
ExecStart=/opt/zerorespond/alert-processor/venv/bin/python3 wazuh_listener.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Installation commands (document these — do not run unless deploying for real):
```bash
sudo cp zerorespond-listener.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zerorespond-listener
sudo systemctl start zerorespond-listener
sudo systemctl status zerorespond-listener
```

Commit:
```bash
git add alert-processor/Dockerfile docker-compose.yml alert-processor/zerorespond-listener.service
git commit -m "feat: dockerize alert-processor, add systemd unit for bare-metal deployments"
```

---

## Day 7 — Final Verification + Week 7 Completion Check

### Task 7.1 — Run the full completion checklist

```bash
TOKEN="eyJ..."  # fresh admin token
BASE="http://localhost:8000"

# Check 1: Evidence upload works
echo "test evidence content" > /tmp/check_evidence.txt
RESP=$(curl -s -X POST $BASE/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/check_evidence.txt" \
  -F "description=Week 7 check")
echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['filename']=='check_evidence.txt'; print('✓ Evidence upload works')"

EVIDENCE_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Check 2: Evidence list works
curl -s $BASE/cases/IR-20260623-0001/evidence -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d) >= 1; print('✓ Evidence list works')"

# Check 3: Evidence download returns original content
curl -s $BASE/evidence/$EVIDENCE_ID/download -H "Authorization: Bearer $TOKEN" \
  -o /tmp/downloaded_check.txt
diff -q /tmp/check_evidence.txt /tmp/downloaded_check.txt > /dev/null \
  && echo "✓ Evidence download matches original file" \
  || echo "✗ Downloaded file differs from original"

# Check 4: Disallowed file type is rejected
echo "bad" > /tmp/check.exe
RESP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/check.exe")
[ "$RESP_CODE" = "400" ] && echo "✓ Disallowed file type rejected (400)" || echo "✗ Expected 400, got $RESP_CODE"

# Check 5: Alert processor is mapping Wazuh alerts correctly
echo "✓ Manual check: trigger a Wazuh alert and confirm it appears in GET /alerts within 5 seconds"

# Check 6: Evidence files exist on disk under the correct case folder
ls data/evidence/IR-20260623-0001/ | grep -c "check_evidence" \
  | grep -q "1" && echo "✓ Evidence file stored on disk in correct case folder"

# Check 7: Frontend evidence upload UI is wired
echo "✓ Manual check: open a case in the browser, drag-drop a file, confirm it appears in the list"
echo "✓ Manual check: click download icon, confirm file downloads with correct name"
echo "✓ Manual check: as admin, click delete icon, confirm file removed from list and disk"
```

---

### Task 7.2 — Verify in PostgreSQL

```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, case_id, filename, file_size, uploaded_by, uploaded_at FROM evidence ORDER BY uploaded_at DESC LIMIT 5;"
```

---

### Task 7.3 — Final commit and tag

```bash
git add .
git commit -m "feat: week 7 complete — evidence management, Wazuh alert-processor integration"
git tag v0.7.0-week7
git push origin main --tags
```

---

## Week 7 Summary

| Day | What you built | Verification |
|-----|----------------|-------------|
| 1 | `evidence.py` schema, `evidence_service.py` with file type/size validation, UUID-prefixed safe filenames | File saved under `data/evidence/{case_id}/`, DB record created |
| 2 | Evidence router — upload, list, download (original filename preserved), delete (admin only) | curl tests: upload, list, download diff matches, type rejection, 403 for analyst |
| 3 | `EvidenceUpload.tsx` — drag-drop zone, file list with icons, authenticated download via blob fetch, admin-only delete | Wired into Case Detail page |
| 4 | Wazuh manager installed/verified, real alert generated and inspected, JSON shape mapping understood | `alerts.json` shows a real brute-force alert with correct structure |
| 5 | `alert-processor/wazuh_listener.py` — tails alerts.json, maps fields, forwards with retry/backoff, skips low-severity noise | Real Wazuh alert appears in ZeroRespond within seconds, gets AI-enriched |
| 6 | Dockerfile + docker-compose service for alert-processor, systemd unit as bare-metal alternative | Both deployment paths documented and ready |
| 7 | 7-check automated checklist + 3 manual UI checks + PostgreSQL verification | All checks pass |

**You are now ready for Week 8 — Reporting Dashboard Enhancements + Hardening.**

---

*ZeroRespond · Manikandan · KCT 2023–2027*
