# ZeroRespond — Week 7 Day 6 & Day 7 Tasks

## Day 6 — Deployment Documentation + Health Verification Script

### Task 6.1 — Create `check_stack.sh`

Create this file in your project root:

```bash
#!/bin/bash
# check_stack.sh — verify all 9 services are reachable
# Run after: docker compose up -d

set -e

echo "=== ZeroRespond Stack Health Check ==="
echo ""

echo "1. PostgreSQL:"
docker compose exec postgres pg_isready -U zr -d zerorespondnd \
  && echo "  ✓ PostgreSQL healthy" || echo "  ✗ PostgreSQL not ready"
echo ""

echo "2. Ollama (via backend network):"
docker compose exec backend curl -s http://ollama:11434/api/tags \
  | python3 -m json.tool | head -5
echo ""

echo "3. Backend:"
curl -s http://localhost:8000/health | python3 -m json.tool \
  && echo "  ✓ Backend healthy" || echo "  ✗ Backend not reachable"
echo ""

echo "4. Backend AI health:"
curl -s http://localhost:8000/health/ai | python3 -m json.tool
echo ""

echo "5. Frontend:"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80)
[ "$HTTP" = "200" ] && echo "  ✓ Frontend reachable (HTTP $HTTP)" \
  || echo "  ✗ Frontend returned HTTP $HTTP"
echo ""

echo "6. Wazuh indexer:"
docker compose exec wazuh.indexer curl -sk \
  -u "${INDEXER_USERNAME:-admin}:${INDEXER_PASSWORD:-SecretPassword}" \
  https://localhost:9200 | python3 -m json.tool | head -5
echo ""

echo "7. Wazuh dashboard:"
HTTP=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443)
[ "$HTTP" = "200" ] || [ "$HTTP" = "302" ] \
  && echo "  ✓ Wazuh dashboard reachable (HTTP $HTTP)" \
  || echo "  ✗ Wazuh dashboard returned HTTP $HTTP"
echo ""

echo "8. Wazuh manager alerts.json:"
docker compose exec wazuh.manager test -f /var/ossec/logs/alerts/alerts.json \
  && echo "  ✓ alerts.json exists inside manager container" \
  || echo "  ✗ alerts.json missing"
echo ""

echo "9. Alert processor:"
docker compose logs alert-processor --tail 5
echo ""

echo "=== Check complete ==="
```

Make it executable:

```bash
chmod +x check_stack.sh
```

---

### Task 6.2 — Create `DEPLOYMENT.md`

Create this file in your project root:

```markdown
# ZeroRespond — Deployment Guide

## Requirements

- Docker Engine 24+ and Docker Compose v2
- Linux host with at least 16GB RAM, 4 CPU cores, 60GB free disk
- Internet access for first boot only (pulls images + qwen2.5:7b model, ~5GB total)

## First-time setup (run once per deployment)

\`\`\`bash
git clone https://github.com/max-mani/ZeroRespond.git zerorespond
cd zerorespond
cp .env.example .env
nano .env   # set real passwords — never use example values in production
./setup.sh
\`\`\`

`setup.sh` does three things:
1. Sets `vm.max_map_count=262144` on the host (required by Wazuh indexer)
2. Generates TLS certificates for Wazuh inter-service communication (one-time)
3. Validates that `.env` exists before proceeding

## Start the platform

\`\`\`bash
docker compose up -d
\`\`\`

First boot takes 3–5 minutes. The Wazuh indexer needs ~60 seconds to
initialize, and `ollama-model-init` pulls `qwen2.5:7b` (~4.7GB) on first
boot only. Subsequent starts take under a minute.

Watch boot progress:

\`\`\`bash
docker compose logs -f
\`\`\`

## Access points

| Service               | URL                           | Notes                              |
|-----------------------|-------------------------------|------------------------------------|
| ZeroRespond frontend  | http://localhost              | Main incident response UI          |
| ZeroRespond API docs  | http://localhost:8000/docs    | FastAPI Swagger UI                 |
| Wazuh dashboard       | https://localhost:8443        | SIEM — accept the self-signed cert |

## First login

Register the first admin user (automatically becomes admin):

\`\`\`bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "you@org.in",
    "password": "YourStrongPassword123",
    "full_name": "Your Name",
    "role": "admin"
  }'
\`\`\`

Then open http://localhost and log in with those credentials.

After logging in, go to **Settings** and fill in your organisation's DPDP
details (organisation name, DPO name, DPO email, CERT-In contact). These
appear on all breach notification PDFs.

## Seed sample data (development/demo only)

\`\`\`bash
docker exec zr-backend python scripts/seed_data.py
docker exec zr-backend python scripts/seed_playbooks.py
\`\`\`

## Generate the alert-processor API token

The alert-processor needs a valid JWT to forward Wazuh alerts to ZeroRespond.
After registering the admin user, run:

\`\`\`bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@org.in","password":"YourStrongPassword123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

sed -i "s/ZERORESPOND_API_TOKEN=.*/ZERORESPOND_API_TOKEN=$TOKEN/" .env

docker compose up -d alert-processor
\`\`\`

> **Note:** This token expires after 8 hours. Regenerate it with the same
> commands if the alert-processor stops forwarding alerts. This is a known
> trade-off — a long-lived service token mechanism is planned for a future
> hardening release.

## Verify the full stack

\`\`\`bash
./check_stack.sh
\`\`\`

## Stop the platform

\`\`\`bash
docker compose down
\`\`\`

Data persists in Docker volumes between restarts.

## Full data wipe (destructive)

\`\`\`bash
docker compose down -v
\`\`\`

This deletes all PostgreSQL data, Wazuh indexer data, and the Ollama model
cache. You will need to re-run `./setup.sh` and re-seed data after this.

## Container overview

| Container             | Role                                         |
|-----------------------|----------------------------------------------|
| zr-postgres           | PostgreSQL 15 — incident and user data       |
| zr-ollama             | Local AI inference — no data leaves the host |
| zr-ollama-init        | One-time model pull on first boot            |
| zr-backend            | FastAPI — REST API, AI enrichment queue      |
| zr-frontend           | React + Nginx — incident response UI         |
| zr-wazuh-manager      | Wazuh SIEM — alert detection and analysis    |
| zr-wazuh-indexer      | OpenSearch — Wazuh alert storage             |
| zr-wazuh-dashboard    | Wazuh UI — https://localhost:8443            |
| zr-alert-processor    | Bridges Wazuh alerts.json → ZeroRespond API  |

## Known limitations (Week 8 hardening targets)

- Alert-processor token expires every 8 hours — manual regeneration needed
- Wazuh indexer port 9200 exposed to host — remove in production deployments
- No Wazuh agents deployed — manager monitors itself only by default
- Change all default passwords in `.env` before any client deployment
```

---

### Task 6.3 — Commit

```bash
git add check_stack.sh DEPLOYMENT.md
git commit -m "docs: check_stack.sh health verification + client deployment guide"
git push origin main
```

---

## Day 7 — Final Verification + Week 7 Completion

### Task 7.1 — Get a fresh token first

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hospital.in","password":"SecurePass123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token acquired: ${TOKEN:0:20}..."
BASE="http://localhost:8000"
```

---

### Task 7.2 — Evidence Checklist (Checks 1–5)

```bash
# Check 1: Evidence upload works
echo "test evidence content — Week 7 check" > /tmp/check_evidence.txt
RESP=$(curl -s -X POST $BASE/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/check_evidence.txt" \
  -F "description=Week 7 completion check")
echo "$RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert d['filename']=='check_evidence.txt', f'Wrong filename: {d}'
assert d['file_size'] > 0, 'File size is 0'
assert d['uploaded_by'] == 'admin@hospital.in', f'Wrong uploader: {d}'
print('✓ Check 1: Evidence upload works')
"

EVIDENCE_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Evidence ID: $EVIDENCE_ID"
```

```bash
# Check 2: Evidence list works
curl -s $BASE/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert len(d) >= 1, f'Expected at least 1 item, got {len(d)}'
print(f'✓ Check 2: Evidence list works ({len(d)} files)')
"
```

```bash
# Check 3: Evidence download returns identical content
curl -s $BASE/evidence/$EVIDENCE_ID/download \
  -H "Authorization: Bearer $TOKEN" \
  -o /tmp/downloaded_check.txt

diff -q /tmp/check_evidence.txt /tmp/downloaded_check.txt > /dev/null \
  && echo "✓ Check 3: Evidence download matches original file" \
  || echo "✗ Check 3: Downloaded file differs from original"
```

```bash
# Check 4: Disallowed file type is rejected
echo "malicious" > /tmp/check.exe
RESP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST $BASE/cases/IR-20260623-0001/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/check.exe")
[ "$RESP_CODE" = "400" ] \
  && echo "✓ Check 4: Disallowed file type rejected (400)" \
  || echo "✗ Check 4: Expected 400, got $RESP_CODE"
```

```bash
# Check 5: File exists on disk in correct folder
COUNT=$(ls data/evidence/IR-20260623-0001/ | grep -c "check_evidence" || true)
[ "$COUNT" -ge "1" ] \
  && echo "✓ Check 5: Evidence file stored on disk in correct case folder" \
  || echo "✗ Check 5: File not found on disk"
```

---

### Task 7.3 — Containerization Checks (Checks 6–10)

```bash
# Check 6: All 9 expected containers are running
echo "Check 6: All 9 containers running"
EXPECTED="zr-postgres zr-ollama zr-backend zr-frontend zr-wazuh-manager zr-wazuh-indexer zr-wazuh-dashboard zr-alert-processor"
RUNNING=$(docker compose ps --status running --format '{{.Name}}')
ALL_OK=true
for c in $EXPECTED; do
  if echo "$RUNNING" | grep -q "$c"; then
    echo "  ✓ $c running"
  else
    echo "  ✗ $c NOT running"
    ALL_OK=false
  fi
done
[ "$ALL_OK" = true ] && echo "✓ Check 6: All containers running"
```

```bash
# Check 7: Backend reaches Ollama through Docker network
curl -s http://localhost:8000/health/ai | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert d['ai_agent']['ollama_running'], 'Ollama not reachable from backend'
print('✓ Check 7: Backend reaches containerized Ollama')
print(f'  Model available: {d[\"ai_agent\"][\"model_available\"]}')
print(f'  Status: {d[\"ai_agent\"][\"status\"]}')
"
```

```bash
# Check 8: Wazuh indexer is healthy
STATUS=$(docker compose ps wazuh.indexer --format '{{.Status}}')
echo "$STATUS" | grep -q "healthy" \
  && echo "✓ Check 8: Wazuh indexer healthy ($STATUS)" \
  || echo "✗ Check 8: Wazuh indexer not healthy — Status: $STATUS"
```

```bash
# Check 9: alerts.json exists inside Wazuh volume
docker compose exec wazuh.manager test -f /var/ossec/logs/alerts/alerts.json \
  && echo "✓ Check 9: alerts.json exists inside Wazuh manager container" \
  || echo "✗ Check 9: alerts.json missing"

# Also confirm alert-processor is reading it
docker compose logs alert-processor --tail 3
```

```bash
# Check 10: Data survives a full stack restart
echo "Check 10: Restarting stack — this takes ~30 seconds..."
docker compose restart
sleep 30

curl -s $BASE/cases/IR-20260623-0001 \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert d['id']=='IR-20260623-0001', f'Case missing after restart: {d}'
print('✓ Check 10: Case data survived full stack restart')
"
```

---

### Task 7.4 — PostgreSQL Evidence Verification

```bash
docker exec zr-postgres psql -U zr -d zerorespondnd \
  -c "SELECT id, case_id, filename, file_size, uploaded_by, uploaded_at
      FROM evidence
      ORDER BY uploaded_at DESC
      LIMIT 5;"
```

Expected output — at least one row with `filename=check_evidence.txt`.

---

### Task 7.5 — Run the Full Health Check Script

```bash
./check_stack.sh
```

All 9 checks should pass with no connection-refused errors.

---

### Task 7.6 — Final Commit and Tag

```bash
git add .
git commit -m "feat: week 7 complete — evidence management + full containerized stack (Wazuh + Ollama via single docker compose up)"
git tag v0.7.0-week7
git push origin main --tags
```

---

## Week 7 Summary

| Day | What you built | Status |
|-----|----------------|--------|
| 1 | Evidence schema + service — file validation, UUID-prefixed storage | ✅ Complete |
| 2 | Evidence router — upload, list, download, delete (admin only) | ✅ Complete |
| 3 | EvidenceUpload.tsx — drag-drop, file list, authenticated download | ✅ Complete |
| 4 | Full containerized stack — Wazuh + Ollama in docker-compose.yml, setup.sh, cert generation | ✅ Complete |
| 5 | alert-processor — tails wazuh_logs Docker volume, maps and forwards alerts with retry | ✅ Complete |
| 6 | check_stack.sh + DEPLOYMENT.md | ✅ Complete after this day |
| 7 | Full 10-check verification — evidence + containerization + restart persistence | ✅ Complete after this day |

**Known trade-offs documented for Week 8 hardening:**
- Alert-processor token expires every 8 hours
- Port 9200 exposed to host — restrict in production
- No Wazuh agents yet — manager monitors itself only
- Default passwords must be changed per deployment

---

*ZeroRespond · Manikandan · KCT 2023–2027*
