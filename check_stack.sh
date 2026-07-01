#!/bin/bash
# check_stack.sh — verify all 9 services are reachable
# Run after: docker compose up -d

echo "=== ZeroRespond Stack Health Check ==="
echo ""

echo "1. PostgreSQL:"
docker compose exec postgres pg_isready -U zr -d zerorespondnd \
  && echo "  ✓ PostgreSQL healthy" || echo "  ✗ PostgreSQL not ready"
echo ""

echo "2. Ollama (via backend AI health check):"
OLLAMA_STATUS=$(curl -s http://localhost:8000/health/ai \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['ai_agent']['status'])")
[ "$OLLAMA_STATUS" = "ready" ] \
  && echo "  ✓ Ollama reachable and model ready" \
  || echo "  ✗ Ollama status: $OLLAMA_STATUS"
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
HTTP=$(curl -sk --max-time 10 -o /dev/null -w "%{http_code}" https://localhost:8443 || echo "000")
[ "$HTTP" = "200" ] || [ "$HTTP" = "302" ] \
  && echo "  ✓ Wazuh dashboard reachable (HTTP $HTTP)" \
  || echo "  ⚠ Wazuh dashboard returned HTTP $HTTP (may still be initializing)"
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