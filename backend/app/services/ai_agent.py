# backend/app/services/ai_agent.py
"""
AI agent for ZeroRespond.
Classifies Wazuh alerts using local Ollama (qwen2.5:7b).
No data leaves the client network.
"""
import logging
from app.services.ollama_client import call_ollama, parse_llm_json
from app.models.case import BreachTypeEnum, SeverityEnum

logger = logging.getLogger(__name__)

# ─── System prompt ────────────────────────────────────────────────────────────
# This prompt is the core of the AI agent. Every word matters.
# Keep it concise — longer prompts increase latency and reduce JSON reliability.

SYSTEM_PROMPT = """You are a cybersecurity incident response AI for Indian organisations.
You classify Wazuh SIEM alerts and return structured JSON only.
No markdown, no explanation, no preamble. Return only a valid JSON object.

Classify every alert into exactly one attack_type:
- ransomware: file encryption, ransom demand, crypto-locker behaviour
- phishing: malicious URLs, email-based attacks, credential harvesting
- unauthorized_access: brute force, failed logins, authentication bypass, port scans
- exfiltration: large data transfers, unusual outbound traffic, data staging
- insider: privilege misuse, after-hours access, internal policy violations

Rules:
- severity must be: critical, high, medium, or low
- mitre_technique must be a real MITRE ATT&CK ID (e.g. T1486, T1566.001, T1110.001)
- confidence is your certainty as a number from 0 to 100
- summary must be plain English readable by a hospital administrator (1-3 sentences)
- immediate_action must be one specific, concrete thing the responder should do right now"""

USER_PROMPT_TEMPLATE = """Classify this Wazuh alert:
Rule ID: {rule_id}
Level: {level} (scale 1-15, 15 is most severe)
Description: {description}
Source IP: {source_ip}
Host: {host}
Groups: {groups}

Return JSON with exactly these keys: attack_type, severity, confidence, summary, mitre_technique, immediate_action"""


async def classify_alert_ai(
    wazuh_rule_id: int,
    level: int,
    description: str,
    source_ip: str | None,
    host: str,
    groups: list[str] | None
) -> dict:
    """
    Classify a Wazuh alert using the local Ollama AI agent.

    Returns a dict with keys:
        attack_type, severity, confidence, summary, mitre_technique, immediate_action

    Raises:
        Exception — if Ollama is unreachable or returns unparseable output.
        Callers should catch this and fall back to classify_alert_basic().
    """
    user_message = USER_PROMPT_TEMPLATE.format(
        rule_id=wazuh_rule_id,
        level=level,
        description=description,
        source_ip=source_ip or "Unknown",
        host=host,
        groups=", ".join(groups) if groups else "None"
    )

    raw = await call_ollama(SYSTEM_PROMPT, user_message)
    result = parse_llm_json(raw)

    # Validate and normalise the returned fields
    result = _validate_and_normalise(result)
    return result


def _validate_and_normalise(result: dict) -> dict:
    """
    Validate AI output and normalise to expected types.
    Fixes common model mistakes without re-calling Ollama.
    """
    # Validate attack_type
    valid_attack_types = {e.value for e in BreachTypeEnum}
    if result.get("attack_type") not in valid_attack_types:
        logger.warning(f"AI returned unknown attack_type '{result.get('attack_type')}', defaulting to unauthorized_access")
        result["attack_type"] = "unauthorized_access"

    # Validate severity
    valid_severities = {e.value for e in SeverityEnum}
    if result.get("severity") not in valid_severities:
        logger.warning(f"AI returned unknown severity '{result.get('severity')}', defaulting to medium")
        result["severity"] = "medium"

    # Validate confidence — clamp to 0-100
    try:
        result["confidence"] = float(result.get("confidence", 50.0))
        result["confidence"] = max(0.0, min(100.0, result["confidence"]))
    except (TypeError, ValueError):
        result["confidence"] = 50.0

    # Validate MITRE technique — basic format check
    mitre = result.get("mitre_technique", "")
    if not isinstance(mitre, str) or not mitre.startswith("T"):
        logger.warning(f"AI returned suspicious MITRE technique '{mitre}'")
        result["mitre_technique"] = mitre  # Keep it, just log the warning

    # Ensure summary and immediate_action are strings
    result["summary"] = str(result.get("summary", "AI classification completed."))
    result["immediate_action"] = str(result.get("immediate_action", "Review the alert and take appropriate action."))

    return result