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

# ZeroRespond — Week 7 Task List (Day 4–7, Revised)
**Phase 7 · Evidence Management + Wazuh Integration — Containerized Deployment**

> **This replaces the original Day 4–7 plan.** The original plan assumed Wazuh installed directly on the host via `wazuh-install.sh`. That approach does not match the deployment goal you actually want: **a client should be able to pull and run the entire ZeroRespond stack — frontend, backend, PostgreSQL, Ollama, and Wazuh (manager + indexer + dashboard) — with a single `docker compose up -d`.**
>
> Days 1–3 (Evidence schema, service, router, frontend upload UI) are unchanged and already complete per your log. This document covers Day 4 onward only.

---

## Why this changes the architecture

Wazuh's officially supported Docker deployment (`wazuh/wazuh-docker`, single-node stack) is itself three containers — `wazuh.manager`, `wazuh.indexer` (OpenSearch-based), `wazuh.dashboard` — not one. There is no lighter "just the manager" Docker image that Wazuh supports for production use; the manager container expects the indexer for alert storage and the dashboard expects the indexer to be healthy before it starts. So "containerize Wazuh" really means "add three more services to docker-compose.yml," not one.

Combined with Postgres, backend, frontend, and now Ollama, your full stack is **eight containers**: `postgres`, `backend`, `frontend`, `ollama`, `wazuh.manager`, `wazuh.indexer`, `wazuh.dashboard`, `alert-processor`.

Two host-level prerequisites are unavoidable and must be documented for the client, because they happen *outside* Docker:

1. **`vm.max_map_count=262144`** must be set on the Docker host kernel — the Wazuh indexer (OpenSearch) will crash-loop without it. This cannot be set from inside a container.
2. **TLS certificates** for inter-component Wazuh communication (manager ↔ indexer ↔ dashboard) must be generated once before first boot, via a separate `docker compose run` step using Wazuh's cert-generator image. This is a one-time setup step, run before `docker compose up -d`, not part of the single up command itself — but it only needs to happen once per deployment, and you script it into one `./setup.sh`.

The result: clients run `./setup.sh` once (cert generation + sysctl check), then `docker compose up -d` every time after. That is the realistic shape of "one command" for a stack this size — Wazuh itself does not offer anything lighter.

---

## Revised Week 7 Architecture

```
zerorespond/
├── docker-compose.yml              ← THE single command: docker compose up -d
├── setup.sh                        ← one-time: certs + sysctl check (run once)
├── generate-indexer-certs.yml      ← cert generation compose file (Wazuh-provided pattern)
├── .env                            ← all secrets/passwords in one place
├── backend/                        ← existing, unchanged
├── frontend/                       ← existing, unchanged
├── alert-processor/                ← existing, unchanged (Day 5 below)
├── config/
│   ├── wazuh_indexer/
│   │   └── wazuh.indexer.yml
│   ├── wazuh_dashboard/
│   │   └── opensearch_dashboards.yml
│   ├── wazuh_cluster/
│   │   └── wazuh_manager.conf
│   └── certs.yml                  ← cert-generator config (hostnames per node)
└── data/
    ├── evidence/                  ← existing
    └── reports/                   ← existing
```

---

## Day 4 — Wazuh in Docker: Certs, Config, and Compose Definition

### Task 4.1 — Host prerequisite: set `vm.max_map_count`

The Wazuh indexer is built on OpenSearch, which memory-maps a large number of files. The Linux default (65530) is too low and the indexer container will crash-loop with `max virtual memory areas vm.max_map_count [65530] is too low`.

```bash
# Apply now (until reboot)
sudo sysctl -w vm.max_map_count=262144

# Persist across reboots
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# Verify
sysctl vm.max_map_count
# Expected: vm.max_map_count = 262144
```

> This is the only step that genuinely cannot be done from inside a container — it changes the host kernel. Document this clearly for any client your platform is deployed to (run as part of `setup.sh` below).

---

### Task 4.2 — Create `.env` for the full stack

```env
# .env — ZeroRespond full stack secrets
# DO NOT COMMIT THIS FILE — add to .gitignore

# PostgreSQL
POSTGRES_DB=zerorespondnd
POSTGRES_USER=zr
POSTGRES_PASSWORD=secret

# Backend
SECRET_KEY=ae133fc4b47eed9d39770a5a7cd8d642038eecb81038d8a46c96eb4df9e43e85
ENVIRONMENT=production

# Ollama
OLLAMA_MODEL=qwen2.5:7b

# Wazuh indexer / dashboard
INDEXER_USERNAME=admin
INDEXER_PASSWORD=ChangeMeStrong123!
DASHBOARD_USERNAME=kibanaserver
DASHBOARD_PASSWORD=ChangeMeStrong123!
WAZUH_API_USER=wazuh-wui
WAZUH_API_PASSWORD=ChangeMeStrong123!

# Alert processor — generated by setup.sh after first admin login, see Day 5
ZERORESPOND_API_TOKEN=
```

Add to `.gitignore` (if not already covered by the existing `.env` rule):
```bash
echo ".env" >> .gitignore
echo "config/wazuh_indexer_ssl_certs/" >> .gitignore
```

---

### Task 4.3 — Create the cert-generator compose file

Wazuh's manager, indexer, and dashboard authenticate to each other over TLS. Certificates are generated once, before first boot, with Wazuh's official cert-generator image.

Create `generate-indexer-certs.yml`:

```yaml
# generate-indexer-certs.yml
services:
  generator:
    image: wazuh/wazuh-certs-generator:0.0.4
    hostname: wazuh-certs-generator
    volumes:
      - ./config/wazuh_indexer_ssl_certs/:/certificates/
      - ./config/certs.yml:/config/certs.yml
```

Create `config/certs.yml`:

```yaml
# config/certs.yml — defines the node names that need certs
nodes:
  indexer:
    - name: wazuh.indexer
  server:
    - name: wazuh.manager
  dashboard:
    - name: wazuh.dashboard
```

---

### Task 4.4 — Create Wazuh indexer config

Create `config/wazuh_indexer/wazuh.indexer.yml`:

```yaml
network.host: "0.0.0.0"
node.name: "wazuh.indexer"
cluster.initial_master_nodes:
  - "wazuh.indexer"
cluster.name: "wazuh-cluster"
discovery.seed_hosts: []
node.max_local_storage_nodes: "3"
path.data: /var/lib/wazuh-indexer
path.logs: /var/log/wazuh-indexer
plugins.security.ssl.http.pemcert_filepath: certs/wazuh.indexer.pem
plugins.security.ssl.http.pemkey_filepath: certs/wazuh.indexer-key.pem
plugins.security.ssl.http.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.ssl.transport.pemcert_filepath: certs/wazuh.indexer.pem
plugins.security.ssl.transport.pemkey_filepath: certs/wazuh.indexer-key.pem
plugins.security.ssl.transport.pemtrustedcas_filepath: certs/root-ca.pem
plugins.security.ssl.http.enabled: true
plugins.security.ssl.transport.enforce_hostname_verification: false
plugins.security.ssl.transport.resolve_hostname: false
plugins.security.authcz.admin_dn:
  - "CN=admin,OU=Wazuh,O=Wazuh,L=California,C=US"
plugins.security.check_snapshot_restore_write_privileges: true
plugins.security.enable_snapshot_restore_privilege: true
plugins.security.nodes_dn:
  - "CN=wazuh.indexer,OU=Wazuh,O=Wazuh,L=California,C=US"
plugins.security.restapi.roles_enabled:
  - "all_access"
  - "security_rest_api_access"
plugins.security.system_indices.enabled: true
plugins.security.system_indices.indices: [
  ".plugins-ml-model", ".plugins-ml-task", ".opendistro-alerting-config",
  ".opendistro-alerting-alert*", ".opendistro-anomaly-results*",
  ".opendistro-anomaly-detector*", ".opendistro-anomaly-checkpoints",
  ".opendistro-anomaly-detection-state", ".opendistro-reports-*",
  ".opensearch-notifications-*", ".opensearch-notebooks",
  ".opensearch-observability", ".ql-datasources", ".opendistro-asynchronous-search-response*",
  ".replication-metadata-store", ".opensearch-knn-models", ".geospatial-ip2geo-data*"
]
cluster.routing.allocation.disk.threshold_enabled: false
compatibility.override_main_response_version: true
```

Create `config/wazuh_dashboard/opensearch_dashboards.yml`:

```yaml
server.host: "0.0.0.0"
server.port: 5601
opensearch.hosts: ["https://wazuh.indexer:9200"]
opensearch.ssl.verificationMode: certificate
opensearch.username: "${INDEXER_USERNAME}"
opensearch.password: "${INDEXER_PASSWORD}"
opensearch.requestHeadersWhitelist: ["securitytenant", "Authorization"]
opensearch_security.multitenancy.enabled: false
opensearch_security.readonly_mode.roles: ["kibana_read_only"]
server.ssl.enabled: true
server.ssl.key: "/usr/share/wazuh-dashboard/certs/wazuh.dashboard-key.pem"
server.ssl.certificate: "/usr/share/wazuh-dashboard/certs/wazuh.dashboard.pem"
opensearch.ssl.certificateAuthorities: ["/usr/share/wazuh-dashboard/certs/root-ca.pem"]
uiSettings.overrides.defaultRoute: "/app/wz-home"
```

Create `config/wazuh_cluster/wazuh_manager.conf` (minimal — extend later with your own detection rules):

```xml
<ossec_config>
  <global>
    <jsonout_output>yes</jsonout_output>
    <alerts_log>yes</alerts_log>
    <logall>no</logall>
    <logall_json>no</logall_json>
  </global>
  <cluster>
    <disabled>yes</disabled>
  </cluster>
</ossec_config>
```

---

### Task 4.5 — Write the full `docker-compose.yml`

This replaces your existing `docker-compose.yml`. It keeps `postgres`, `backend`, `frontend` exactly as they were, adds `ollama`, and adds the three Wazuh containers plus `alert-processor`.

```yaml
# docker-compose.yml
services:

  # ─── PostgreSQL Database ─────────────────────────────────────────────────
  postgres:
    image: postgres:15-alpine
    container_name: zr-postgres
    environment:
      POSTGRES_DB:       ${POSTGRES_DB}
      POSTGRES_USER:     ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - zr_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - zr-network
    restart: unless-stopped

  # ─── Ollama — local AI inference, air-gapped ──────────────────────────────
  ollama:
    image: ollama/ollama:latest
    container_name: zr-ollama
    volumes:
      - zr_ollama_data:/root/.ollama
    networks:
      - zr-network
    restart: unless-stopped
    # GPU passthrough (uncomment if the deployment host has an NVIDIA GPU):
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  # Pulls the model once on first boot, then exits. Backend retries until ready.
  ollama-model-init:
    image: ollama/ollama:latest
    container_name: zr-ollama-init
    depends_on:
      - ollama
    entrypoint: ["/bin/sh", "-c"]
    command: ["sleep 5 && OLLAMA_HOST=http://ollama:11434 ollama pull ${OLLAMA_MODEL}"]
    networks:
      - zr-network
    restart: "no"

  # ─── FastAPI Backend ─────────────────────────────────────────────────────
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: zr-backend
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      OLLAMA_URL:   http://ollama:11434
      OLLAMA_MODEL: ${OLLAMA_MODEL}
      SECRET_KEY:   ${SECRET_KEY}
      ENVIRONMENT:  ${ENVIRONMENT}
    volumes:
      - ./data/reports:/data/reports
      - ./data/evidence:/data/evidence
      - ./backend/templates:/app/templates
    depends_on:
      postgres:
        condition: service_healthy
      ollama:
        condition: service_started
    ports:
      - "8000:8000"
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

  # ─── Wazuh Manager ─────────────────────────────────────────────────────────
  wazuh.manager:
    image: wazuh/wazuh-manager:4.14.5
    hostname: wazuh.manager
    container_name: zr-wazuh-manager
    restart: unless-stopped
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 655360
        hard: 655360
    ports:
      - "1514:1514"
      - "1515:1515"
      - "514:514/udp"
      - "55000:55000"
    environment:
      INDEXER_URL: https://wazuh.indexer:9200
      INDEXER_USERNAME: ${INDEXER_USERNAME}
      INDEXER_PASSWORD: ${INDEXER_PASSWORD}
      FILEBEAT_SSL_VERIFICATION_MODE: full
      SSL_CERTIFICATE_AUTHORITIES: /etc/ssl/root-ca.pem
      SSL_CERTIFICATE: /etc/ssl/filebeat.pem
      SSL_KEY: /etc/ssl/filebeat.key
      API_USERNAME: ${WAZUH_API_USER}
      API_PASSWORD: ${WAZUH_API_PASSWORD}
    volumes:
      - wazuh_api_configuration:/var/ossec/api/configuration
      - wazuh_etc:/var/ossec/etc
      - wazuh_logs:/var/ossec/logs
      - wazuh_queue:/var/ossec/queue
      - wazuh_var_multigroups:/var/ossec/var/multigroups
      - wazuh_integrations:/var/ossec/integrations
      - wazuh_active_response:/var/ossec/active-response/bin
      - wazuh_agentless:/var/ossec/agentless
      - wazuh_wodles:/var/ossec/wodles
      - ./config/wazuh_indexer_ssl_certs/root-ca-manager.pem:/etc/ssl/root-ca.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.manager.pem:/etc/ssl/filebeat.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.manager-key.pem:/etc/ssl/filebeat.key
      - ./config/wazuh_cluster/wazuh_manager.conf:/wazuh-config-mount/etc/ossec.conf
    depends_on:
      - wazuh.indexer
    networks:
      - zr-network

  # ─── Wazuh Indexer (OpenSearch) ─────────────────────────────────────────────
  wazuh.indexer:
    image: wazuh/wazuh-indexer:4.14.5
    hostname: wazuh.indexer
    container_name: zr-wazuh-indexer
    restart: unless-stopped
    ports:
      - "9200:9200"
    environment:
      OPENSEARCH_JAVA_OPTS: "-Xms1g -Xmx1g"
      OPENSEARCH_INITIAL_ADMIN_PASSWORD: ${INDEXER_PASSWORD}
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    volumes:
      - zr_wazuh_indexer_data:/var/lib/wazuh-indexer
      - ./config/wazuh_indexer_ssl_certs/root-ca.pem:/usr/share/wazuh-indexer/certs/root-ca.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.indexer-key.pem:/usr/share/wazuh-indexer/certs/wazuh-indexer-key.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.indexer.pem:/usr/share/wazuh-indexer/certs/wazuh-indexer.pem
      - ./config/wazuh_indexer_ssl_certs/admin.pem:/usr/share/wazuh-indexer/certs/admin.pem
      - ./config/wazuh_indexer_ssl_certs/admin-key.pem:/usr/share/wazuh-indexer/certs/admin-key.pem
      - ./config/wazuh_indexer/wazuh.indexer.yml:/usr/share/wazuh-indexer/opensearch.yml
    healthcheck:
      test: ["CMD-SHELL", "curl -sk https://localhost:9200 -u ${INDEXER_USERNAME}:${INDEXER_PASSWORD} | grep -q 'wazuh-indexer'"]
      interval: 30s
      timeout: 10s
      retries: 5
    networks:
      - zr-network

  # ─── Wazuh Dashboard ─────────────────────────────────────────────────────────
  wazuh.dashboard:
    image: wazuh/wazuh-dashboard:4.14.5
    hostname: wazuh.dashboard
    container_name: zr-wazuh-dashboard
    restart: unless-stopped
    ports:
      - "8443:5601"     # exposed on 8443 to avoid colliding with ZeroRespond frontend on 80/443
    environment:
      INDEXER_USERNAME: ${INDEXER_USERNAME}
      INDEXER_PASSWORD: ${INDEXER_PASSWORD}
      WAZUH_API_URL: https://wazuh.manager
      DASHBOARD_USERNAME: ${DASHBOARD_USERNAME}
      DASHBOARD_PASSWORD: ${DASHBOARD_PASSWORD}
      API_USERNAME: ${WAZUH_API_USER}
      API_PASSWORD: ${WAZUH_API_PASSWORD}
    volumes:
      - ./config/wazuh_indexer_ssl_certs/wazuh.dashboard.pem:/usr/share/wazuh-dashboard/certs/wazuh-dashboard.pem
      - ./config/wazuh_indexer_ssl_certs/wazuh.dashboard-key.pem:/usr/share/wazuh-dashboard/certs/wazuh-dashboard-key.pem
      - ./config/wazuh_indexer_ssl_certs/root-ca.pem:/usr/share/wazuh-dashboard/certs/root-ca.pem
      - ./config/wazuh_dashboard/opensearch_dashboards.yml:/usr/share/wazuh-dashboard/config/opensearch_dashboards.yml
      - wazuh_dashboard_config:/usr/share/wazuh-dashboard/data/wazuh/config
      - wazuh_dashboard_custom:/usr/share/wazuh-dashboard/plugins/wazuh/public/assets/custom
    depends_on:
      wazuh.indexer:
        condition: service_healthy
    links:
      - wazuh.indexer:wazuh.indexer
      - wazuh.manager:wazuh.manager
    networks:
      - zr-network

  # ─── Alert Processor — bridges Wazuh alerts.json → ZeroRespond API ─────────
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
      - wazuh_logs:/wazuh-logs:ro
    depends_on:
      - backend
      - wazuh.manager
    networks:
      - zr-network
    restart: unless-stopped

# ─── Volumes ──────────────────────────────────────────────────────────────────
volumes:
  zr_pgdata:
    name: zr_pgdata
  zr_ollama_data:
    name: zr_ollama_data
  zr_wazuh_indexer_data:
    name: zr_wazuh_indexer_data
  wazuh_api_configuration:
  wazuh_etc:
  wazuh_logs:
  wazuh_queue:
  wazuh_var_multigroups:
  wazuh_integrations:
  wazuh_active_response:
  wazuh_agentless:
  wazuh_wodles:
  wazuh_dashboard_config:
  wazuh_dashboard_custom:

# ─── Networks ─────────────────────────────────────────────────────────────────
networks:
  zr-network:
    name: zr-network
    driver: bridge
```

> **Notes on the `alert-processor` volume mount:** instead of bind-mounting the host's `/var/ossec/logs/alerts` (which no longer exists on the host now that Wazuh runs in Docker), `alert-processor` mounts the **named Docker volume** `wazuh_logs` read-only. This is the same volume the `wazuh.manager` container writes `alerts.json` to. This is the key change from the original Day 5/6 plan — no host filesystem dependency at all.
>
> **Port 9200 warning:** the indexer port is exposed here for local debugging convenience. For an actual client deployment (hospital/college network), remove the `9200:9200` mapping from `wazuh.indexer` — the indexer should only be reachable from inside `zr-network`, never from outside. Document this as a hardening step in Week 8.

---

### Task 4.6 — Write `setup.sh` — the one-time bootstrap script

```bash
#!/bin/bash
# setup.sh — One-time setup before first `docker compose up -d`
# Run this ONCE per deployment. Safe to re-run (idempotent on certs).
set -e

echo "=== ZeroRespond Setup ==="

echo "[1/3] Checking vm.max_map_count (required by Wazuh indexer)..."
CURRENT=$(sysctl -n vm.max_map_count)
if [ "$CURRENT" -lt 262144 ]; then
  echo "  vm.max_map_count is $CURRENT — raising to 262144..."
  sudo sysctl -w vm.max_map_count=262144
  if ! grep -q "vm.max_map_count" /etc/sysctl.conf 2>/dev/null; then
    echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
  fi
else
  echo "  OK — vm.max_map_count is $CURRENT"
fi

echo "[2/3] Generating Wazuh TLS certificates (one-time)..."
if [ -f "config/wazuh_indexer_ssl_certs/root-ca.pem" ]; then
  echo "  Certs already exist — skipping. Delete config/wazuh_indexer_ssl_certs/ to regenerate."
else
  mkdir -p config/wazuh_indexer_ssl_certs
  docker compose -f generate-indexer-certs.yml run --rm generator
  # The manager needs its own copy of root-ca under a distinct filename per the volume mount above
  cp config/wazuh_indexer_ssl_certs/root-ca.pem config/wazuh_indexer_ssl_certs/root-ca-manager.pem
  echo "  Certs generated in config/wazuh_indexer_ssl_certs/"
fi

echo "[3/3] Checking .env exists..."
if [ ! -f ".env" ]; then
  echo "  ERROR: .env not found. Copy .env.example to .env and fill in passwords first."
  exit 1
fi
echo "  OK — .env present"

echo ""
echo "=== Setup complete ==="
echo "Run the stack with:"
echo "  docker compose up -d"
echo ""
echo "First boot will take several minutes — the Wazuh indexer needs ~1 min to"
echo "initialize, and ollama-model-init needs to pull qwen2.5:7b (~4.7GB)."
echo "Watch progress with: docker compose logs -f"
```

```bash
chmod +x setup.sh
```

Commit:
```bash
git add docker-compose.yml generate-indexer-certs.yml setup.sh config/ .env.example
git commit -m "feat: containerize full stack — Wazuh (manager/indexer/dashboard) + Ollama via docker-compose"
```

> **Do not commit `.env` or `config/wazuh_indexer_ssl_certs/`** — both contain secrets/private keys. Create a `.env.example` with the same keys but placeholder values for the repo.

---

## Day 5 — Alert Processor (Updated for Containerized Wazuh)

The `alert-processor` service from your original Day 5 plan is **unchanged in logic** — it still tails `alerts.json` and forwards mapped alerts to `/alerts` with retry/backoff. The only change is *where it reads from*: a Docker named volume (`wazuh_logs`) instead of a host bind-mount, since Wazuh itself now lives in a container.

### Task 5.1 — `alert-processor/wazuh_listener.py` (no code changes needed)

Your existing file from the original Week 7 plan works as-is — `WAZUH_ALERTS_LOG` is just an environment variable, and `/wazuh-logs/alerts.json` resolves correctly whether that path comes from a host bind-mount or a Docker volume mount. No changes required to `wazuh_listener.py`, `requirements.txt`, or `Dockerfile`.

### Task 5.2 — Generate the API token for `alert-processor`

This step now happens *after* `docker compose up -d` (you need the backend running and an admin user registered first):

```bash
# 1. Bring the stack up
docker compose up -d

# 2. Watch logs until backend is healthy
docker compose logs -f backend
# Wait for: "ZeroRespond API started — queue worker running."

# 3. Register the first admin user (becomes admin automatically)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hospital.in","password":"SecurePass123","full_name":"Admin","role":"admin"}'

# 4. Log in and capture the token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hospital.in","password":"SecurePass123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"

# 5. Put it in .env
sed -i "s/ZERORESPOND_API_TOKEN=.*/ZERORESPOND_API_TOKEN=$TOKEN/" .env

# 6. Restart alert-processor to pick up the new token
docker compose up -d alert-processor
```

> **Production note:** this token expires after 8 hours (per `ACCESS_TOKEN_EXPIRE_HOURS` in `auth_service.py`). For a real client deployment, either issue a long-lived service-account token or build a small refresh mechanism into `wazuh_listener.py` — flag this as a Week 8 hardening task, do not solve it this week.

### Task 5.3 — Verify Wazuh is alive and generating alerts

```bash
# Check all containers are up and healthy
docker compose ps

# Expected (eventually, after ~1-2 min for indexer + dashboard):
# zr-postgres            running (healthy)
# zr-ollama               running
# zr-backend              running
# zr-frontend             running
# zr-wazuh-indexer        running (healthy)
# zr-wazuh-manager        running
# zr-wazuh-dashboard      running
# zr-alert-processor      running

# Tail manager logs to confirm it's processing events
docker compose logs -f wazuh.manager

# Generate a test alert FROM INSIDE the manager container (since there's no
# host agent installed by default — the manager container itself can simulate one):
docker compose exec wazuh.manager bash -c \
  "for i in {1..6}; do echo 'Failed password for invalid user test from 127.0.0.1 port 22 ssh2' >> /var/ossec/logs/active-responses.log; done"

# Watch the alert-processor pick it up
docker compose logs -f alert-processor
# Expected: "Forwarded alert ... (status 201)"
```

> If no agents are connected, the manager has limited log sources to alert on by default. A more realistic Day 5 verification is to install a Wazuh **agent** on a second test VM or container and point it at `wazuh.manager:1514` — this is a Week 8 task (multi-host monitoring), not required to prove Day 5's pipeline works. For now, confirming the manager container is healthy and `alerts.json` exists inside the `wazuh_logs` volume is sufficient:

```bash
docker compose exec wazuh.manager ls -la /var/ossec/logs/alerts/
docker compose exec wazuh.manager tail -5 /var/ossec/logs/alerts/alerts.json
```

Commit:
```bash
git add alert-processor/
git commit -m "docs: alert-processor verified against containerized Wazuh volume mount"
```

---

## Day 6 — Single-Command Verification + README for Clients

The original Day 6 (Dockerfile + systemd) is no longer needed — everything is already in `docker-compose.yml` from Day 4, and there's no host-installed Wazuh to write a systemd unit for. Day 6 instead focuses on proving the "one command" promise actually holds, end to end, from a clean clone.

### Task 6.1 — Clean-slate deployment test

This is the test that matters most: simulate what a client does.

```bash
# Simulate a fresh client machine — wipe all ZeroRespond volumes and containers
docker compose down -v
docker volume ls | grep zr_  # confirm nothing zr_-prefixed remains, except wazuh_* if -v missed any
docker volume prune -f

# Re-clone (or just cd into a fresh checkout) and run the documented sequence:
cp .env.example .env
# (edit .env with real passwords)
./setup.sh
docker compose up -d
```

Watch the boot order:
```bash
docker compose logs -f
```

Expected order over the first 2–3 minutes:
1. `postgres` becomes healthy
2. `ollama` starts; `ollama-model-init` begins pulling `qwen2.5:7b` (~4.7GB — this is the slowest step on first boot)
3. `wazuh.indexer` starts, takes ~60s to report healthy
4. `wazuh.manager` and `backend` start once their dependencies are healthy
5. `wazuh.dashboard` starts once the indexer is healthy
6. `frontend` and `alert-processor` come up last

### Task 6.2 — Full health verification script

```bash
#!/bin/bash
# check_stack.sh — verify all 8 services are reachable

echo "1. PostgreSQL:"
docker compose exec postgres pg_isready -U zr -d zerorespondnd

echo "2. Ollama:"
curl -s http://localhost:8000 > /dev/null  # placeholder, ollama has no host port by default
docker compose exec backend curl -s http://ollama:11434/api/tags | python3 -m json.tool | head -10

echo "3. Backend:"
curl -s http://localhost:8000/health | python3 -m json.tool

echo "4. Backend AI health (confirms Ollama + model are reachable from backend):"
curl -s http://localhost:8000/health/ai | python3 -m json.tool

echo "5. Frontend:"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:80

echo "6. Wazuh indexer:"
docker compose exec wazuh.indexer curl -sk -u admin:${INDEXER_PASSWORD:-ChangeMeStrong123!} \
  https://localhost:9200 | python3 -m json.tool | head -5

echo "7. Wazuh dashboard:"
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://localhost:8443

echo "8. Alert processor:"
docker compose logs alert-processor --tail 5
```

Expected: every step returns a 200/healthy response with no connection-refused errors. If `/health/ai` reports `model_not_found`, the `ollama-model-init` pull (Day 4) is likely still in progress — check with `docker compose logs ollama-model-init`.

### Task 6.3 — Write the client-facing `DEPLOYMENT.md`

```markdown
# ZeroRespond — Deployment Guide

## Requirements
- Docker Engine 24+ and Docker Compose v2
- Linux host (native or WSL2) with at least 16GB RAM, 4 CPU cores, 60GB free disk
- Internet access for first boot only (pulls images + the qwen2.5:7b model, ~5GB total)

## First-time setup (run once)

```bash
git clone <your-repo-url> zerorespond
cd zerorespond
cp .env.example .env
nano .env   # set real passwords — do not use the example values in production
./setup.sh
```

## Start the platform

```bash
docker compose up -d
```

First boot takes 3–5 minutes (downloading the AI model and initializing the
Wazuh indexer). Subsequent starts take under a minute.

## Access points

| Service              | URL                          |
|-----------------------|-------------------------------|
| ZeroRespond frontend  | http://localhost              |
| ZeroRespond API docs  | http://localhost:8000/docs    |
| Wazuh dashboard       | https://localhost:8443        |

## Stop the platform

```bash
docker compose down
```

Data persists in Docker volumes between restarts. To fully wipe all data
(including the Postgres database and Wazuh indexer data):

```bash
docker compose down -v
```

## First login

1. Register the first admin user (becomes admin automatically):
   ```bash
   curl -X POST http://localhost:8000/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"you@org.in","password":"YourPassword123","role":"admin"}'
   ```
2. Open http://localhost and log in.
3. Go to Settings and fill in your organisation's DPDP details (DPO name, email, CERT-In contact).
```

Commit:
```bash
git add DEPLOYMENT.md check_stack.sh
git commit -m "docs: client deployment guide for single-command full-stack startup"
```

---

## Day 7 — Final Verification + Week 7 Completion Check

### Task 7.1 — Run the evidence checklist (unchanged from original Day 7, Task 7.1)

These checks don't depend on the Wazuh deployment method — re-run exactly as originally written, against the now-containerized backend:

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

# Check 5: evidence files exist on disk under the correct case folder
ls data/evidence/IR-20260623-0001/ | grep -c "check_evidence" \
  | grep -q "1" && echo "✓ Evidence file stored on disk in correct case folder"
```

### Task 7.2 — New containerization-specific checks

```bash
echo "Check 6: All 8 expected containers are running"
EXPECTED="zr-postgres zr-ollama zr-backend zr-frontend zr-wazuh-manager zr-wazuh-indexer zr-wazuh-dashboard zr-alert-processor"
RUNNING=$(docker compose ps --status running --format '{{.Name}}')
for c in $EXPECTED; do
  echo "$RUNNING" | grep -q "$c" && echo "  ✓ $c running" || echo "  ✗ $c NOT running"
done

echo "Check 7: Backend can reach Ollama through the Docker network (not localhost)"
curl -s http://localhost:8000/health/ai | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['ai_agent']['ollama_running']; print('✓ Backend reaches containerized Ollama')"

echo "Check 8: Wazuh indexer is healthy"
docker compose ps wazuh.indexer --format '{{.Status}}' | grep -q "healthy" \
  && echo "✓ Wazuh indexer healthy" || echo "✗ Wazuh indexer not healthy yet — may need more boot time"

echo "Check 9: alerts.json exists inside the Wazuh volume and alert-processor can read it"
docker compose exec wazuh.manager test -f /var/ossec/logs/alerts/alerts.json \
  && echo "✓ alerts.json exists" || echo "✗ alerts.json missing"

echo "Check 10: A full stack restart preserves data (no data loss on restart)"
docker compose restart
sleep 15
curl -s $BASE/cases/IR-20260623-0001 -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['id']=='IR-20260623-0001'; print('✓ Case data survived restart')"
```

### Task 7.3 — Verify in PostgreSQL (unchanged)

```bash
docker exec -it zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, case_id, filename, file_size, uploaded_by, uploaded_at FROM evidence ORDER BY uploaded_at DESC LIMIT 5;"
```

### Task 7.4 — Final commit and tag

```bash
git add .
git commit -m "feat: week 7 complete — evidence management + full containerized stack (Wazuh + Ollama via single docker compose up)"
git tag v0.7.0-week7
git push origin main --tags
```

---

## Week 7 Summary (Revised)

| Day | What you built | Verification |
|-----|----------------|---------------|
| 1 | `evidence.py` schema, `evidence_service.py` with validation, UUID-prefixed safe filenames | *(unchanged — already completed)* |
| 2 | Evidence router — upload, list, download, delete (admin only) | *(unchanged — already completed)* |
| 3 | `EvidenceUpload.tsx` drag-drop component wired into Case Detail page | *(unchanged — already completed)* |
| 4 | Full containerized stack: `docker-compose.yml` with Wazuh manager + indexer + dashboard + Ollama added alongside existing postgres/backend/frontend; cert generation (`generate-indexer-certs.yml`); `setup.sh` one-time bootstrap | `docker compose ps` shows all containers running; indexer reports healthy |
| 5 | `alert-processor` unchanged in code, repointed at the `wazuh_logs` Docker volume instead of a host bind-mount; admin token generation flow documented | `alert-processor` logs show forwarded alerts; `alerts.json` confirmed inside the manager container |
| 6 | Clean-slate deployment test proving the single-command promise; `check_stack.sh` health verification; client-facing `DEPLOYMENT.md` | Fresh clone → `./setup.sh` → `docker compose up -d` brings up a fully working platform with no manual host installation steps |
| 7 | Full evidence checklist (unchanged) + 5 new containerization checks (container count, Ollama reachability, indexer health, alerts.json presence, restart data persistence) | All checks pass |

**Deployment model achieved:** a client clones the repo, fills in `.env`, runs `./setup.sh` once, then `docker compose up -d` from then on — frontend, backend, database, AI model, and full Wazuh SIEM all come up together with no separate host installation of Wazuh or Ollama required.

**Known trade-offs to revisit in Week 8 (hardening):**
- `alert-processor`'s API token expires every 8 hours — needs a refresh mechanism or long-lived service token.
- Wazuh indexer port `9200` should not be exposed to the host in a real client network — restrict to `zr-network` only.
- No Wazuh *agents* are deployed yet — the manager container alone has limited log sources. Installing agents on monitored endpoints (or configuring syslog forwarding into the manager) is the next real milestone for live detection.
- Default Wazuh/indexer passwords in `.env.example` must be changed per deployment — document this loudly for any client handoff.

---

*ZeroRespond · Manikandan · KCT 2023–2027*
