# ZeroRespond Daily Startup Checklist

## 1. Check Docker Status

```bash
docker ps
```

If the PostgreSQL container is not running:

```bash
docker start zr-postgres
```

Verify it is running:

```bash
docker ps
```

---

## 2. Manage Ollama Service

### Check Status

```bash
systemctl status ollama
```

### Restart Ollama

```bash
sudo systemctl restart ollama
```

### Stop Ollama

```bash
sudo systemctl stop ollama
```

### Start Ollama

```bash
sudo systemctl start ollama
```

### View Live Logs

```bash
journalctl -u ollama -f
```

### Verify Installed Models

```bash
ollama list
```

---

## 3. Start FastAPI Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

---

## 4. Quick Health Checks

### PostgreSQL Container

```bash
docker ps
```

### Ollama API

```bash
curl http://localhost:11434/api/tags
```

### FastAPI Health Endpoint

```bash
curl http://localhost:8000/health
```

Expected Response:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "development"
}
```

---

## Complete Startup Sequence

```bash
docker start zr-postgres

sudo systemctl start ollama

ollama list

cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```
