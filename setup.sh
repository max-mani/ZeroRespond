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
  echo "  Certs already exist — skipping generation."
else
  mkdir -p config/wazuh_indexer_ssl_certs
  docker compose -f generate-indexer-certs.yml run --rm generator
  # The manager needs its own copy of root-ca under a distinct filename per the volume mount above
  cp config/wazuh_indexer_ssl_certs/root-ca.pem config/wazuh_indexer_ssl_certs/root-ca-manager.pem
  echo "  Certs generated in config/wazuh_indexer_ssl_certs/"
fi

echo "  Ensuring cert permissions are readable by Docker containers..."
chmod 755 config/wazuh_indexer_ssl_certs 2>/dev/null || sudo chmod 755 config/wazuh_indexer_ssl_certs
chmod 644 config/wazuh_indexer_ssl_certs/*.pem 2>/dev/null || sudo chmod 644 config/wazuh_indexer_ssl_certs/*.pem

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