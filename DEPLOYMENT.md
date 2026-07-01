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