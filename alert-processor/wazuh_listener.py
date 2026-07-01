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

    while not ALERTS_LOG.exists():
        logger.warning(f"Alerts log not found at {ALERTS_LOG}, waiting for Wazuh...")
        time.sleep(5)

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