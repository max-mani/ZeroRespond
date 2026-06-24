#!/usr/bin/env python3
# backend/scripts/seed_data.py
"""
Run this to populate the database with sample cases and alerts for development.
Usage: cd backend && python scripts/seed_data.py
WARNING: Clears all existing cases and alerts before seeding. Dev only.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.case import Case, SeverityEnum, StatusEnum, BreachTypeEnum
from datetime import datetime, timezone, timedelta

def seed():
    db = SessionLocal()
    try:
        # Clear existing data (dev only!)
        db.query(Case).delete()
        db.query(Alert).delete()
        db.commit()
        print("Cleared existing cases and alerts.")

        # --- Sample Alerts ---
        alerts = [
            Alert(id="seed-alert-001", wazuh_rule_id=5710, level=12,
                  description="SSH brute force — 500 failed logins in 2 minutes",
                  source_ip="203.0.113.42", host="webserver01",
                  groups=["authentication_failed", "sshd"],
                  raw_json={"rule_id": "5710", "level": 12, "host": "webserver01"}),

            Alert(id="seed-alert-002", wazuh_rule_id=87105, level=14,
                  description="Malicious URL detected in email attachment",
                  source_ip="198.51.100.7", host="workstation-finance-03",
                  groups=["phish", "malicious_url"],
                  raw_json={"rule_id": "87105", "level": 14, "host": "workstation-finance-03"}),

            Alert(id="seed-alert-003", wazuh_rule_id=92001, level=15,
                  description="Ransomware signature detected — files being encrypted",
                  source_ip=None, host="fileserver01",
                  groups=["ransomware", "encrypt"],
                  raw_json={"rule_id": "92001", "level": 15, "host": "fileserver01"}),

            Alert(id="seed-alert-004", wazuh_rule_id=61002, level=10,
                  description="Large outbound data transfer detected — potential exfiltration",
                  source_ip="10.0.0.45", host="db-server-01",
                  groups=["exfil", "data_leak"],
                  raw_json={"rule_id": "61002", "level": 10, "host": "db-server-01"}),

            Alert(id="seed-alert-005", wazuh_rule_id=40111, level=9,
                  description="Privileged account access outside business hours",
                  source_ip="10.0.0.12", host="hr-workstation-02",
                  groups=["insider", "privilege"],
                  raw_json={"rule_id": "40111", "level": 9, "host": "hr-workstation-02"}),
        ]

        for alert in alerts:
            db.add(alert)
        db.commit()
        print(f"Seeded {len(alerts)} alerts.")

        # --- Sample Cases ---
        now = datetime.now(timezone.utc)
        cases = [
            Case(id="IR-20260623-0001", title="SSH Brute Force on webserver01",
                 severity=SeverityEnum.high, status=StatusEnum.investigating,
                 breach_type=BreachTypeEnum.unauthorized_access,
                 source_ip="203.0.113.42", source_host="webserver01",
                 alert_id="seed-alert-001", assigned_to="manikandan@org.in",
                 data_categories="Credentials", persons_affected=0,
                 ai_summary="Sustained brute force attack from single IP. 500 failed SSH attempts in 2 minutes suggests automated tooling (Hydra or Medusa). No successful login detected.",
                 ai_confidence=91.5, ai_mitre="T1110.001",
                 immediate_action="Block IP 203.0.113.42 at firewall. Review /var/log/auth.log on webserver01.",
                 detected_at=now - timedelta(hours=3)),

            Case(id="IR-20260623-0002", title="Phishing Attack on Finance Team",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.phishing,
                 source_ip="198.51.100.7", source_host="workstation-finance-03",
                 alert_id="seed-alert-002", assigned_to=None,
                 data_categories="Credentials, PII", persons_affected=12,
                 ai_summary="Malicious URL embedded in email attachment. Finance team targeted. Credential harvesting page detected.",
                 ai_confidence=87.0, ai_mitre="T1566.001",
                 immediate_action="Isolate workstation-finance-03. Notify finance team to change passwords immediately.",
                 detected_at=now - timedelta(hours=1)),

            Case(id="IR-20260623-0003", title="Ransomware Detected on fileserver01",
                 severity=SeverityEnum.critical, status=StatusEnum.contained,
                 breach_type=BreachTypeEnum.ransomware,
                 source_ip=None, source_host="fileserver01",
                 alert_id="seed-alert-003", assigned_to="manikandan@org.in",
                 data_categories="PII, Financial, Health", persons_affected=450,
                 ai_summary="Ransomware signatures detected. Files actively being encrypted. Lateral movement risk from fileserver01 to backup systems.",
                 ai_confidence=97.2, ai_mitre="T1486",
                 immediate_action="IMMEDIATELY isolate fileserver01 from network. Do NOT shut down — preserve RAM for forensics. Activate backup restore plan.",
                 detected_at=now - timedelta(hours=6)),

            Case(id="IR-20260623-0004", title="Suspected Data Exfiltration from DB Server",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.exfiltration,
                 source_ip="10.0.0.45", source_host="db-server-01",
                 alert_id="seed-alert-004", assigned_to=None,
                 data_categories="PII, Health", persons_affected=None,
                 ai_summary="Anomalous outbound traffic (4.2GB in 15 minutes) from database server to external IP. Pattern consistent with automated exfiltration tool.",
                 ai_confidence=78.5, ai_mitre="T1041",
                 immediate_action="Capture network traffic dump. Block outbound connections from db-server-01. Audit database access logs.",
                 detected_at=now - timedelta(minutes=45)),

            Case(id="IR-20260623-0005", title="Insider Access Anomaly — HR Workstation",
                 severity=SeverityEnum.medium, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.insider,
                 source_ip="10.0.0.12", source_host="hr-workstation-02",
                 alert_id="seed-alert-005", assigned_to=None,
                 data_categories="PII", persons_affected=None,
                 ai_summary="Privileged account accessed sensitive HR records at 2:30 AM — outside business hours. No scheduled maintenance active. Possible insider threat or compromised credential.",
                 ai_confidence=65.0, ai_mitre="T1078",
                 immediate_action="Review access logs for hr-workstation-02. Suspend privileged account pending investigation. Check if badge access matches digital access.",
                 detected_at=now - timedelta(minutes=20)),
        ]

        for case in cases:
            db.add(case)
        db.commit()
        print(f"Seeded {len(cases)} cases.")
        print("\nSeed complete. Cases created:")
        for c in cases:
            print(f"  {c.id} — {c.title} [{c.severity.value.upper()}] [{c.status.value}]")

    finally:
        db.close()

if __name__ == "__main__":
    seed()

# Add to the bottom of backend/scripts/seed_data.py

def seed_without_ai():
    """
    Seed cases WITHOUT AI fields so you can test the enrichment pipeline.
    Usage: python scripts/seed_data.py --no-ai
    """
    db = SessionLocal()
    try:
        db.query(Case).delete()
        db.query(Alert).delete()
        db.commit()

        # Same alerts as the main seed function
        alerts = [
            Alert(id="seed-alert-001", wazuh_rule_id=5710, level=12,
                  description="SSH brute force — 500 failed logins in 2 minutes",
                  source_ip="203.0.113.42", host="webserver01",
                  groups=["authentication_failed", "sshd"],
                  raw_json={"rule_id": "5710", "level": 12, "host": "webserver01"}),
            Alert(id="seed-alert-002", wazuh_rule_id=87105, level=14,
                  description="Malicious URL detected in email attachment",
                  source_ip="198.51.100.7", host="workstation-finance-03",
                  groups=["phish", "malicious_url"],
                  raw_json={"rule_id": "87105", "level": 14}),
            Alert(id="seed-alert-003", wazuh_rule_id=92001, level=15,
                  description="Ransomware signature detected — files being encrypted",
                  source_ip=None, host="fileserver01",
                  groups=["ransomware", "encrypt"],
                  raw_json={"rule_id": "92001", "level": 15}),
            Alert(id="seed-alert-004", wazuh_rule_id=61002, level=10,
                  description="Large outbound data transfer detected",
                  source_ip="10.0.0.45", host="db-server-01",
                  groups=["exfil", "data_leak"],
                  raw_json={"rule_id": "61002", "level": 10}),
            Alert(id="seed-alert-005", wazuh_rule_id=40111, level=9,
                  description="Privileged account access outside business hours",
                  source_ip="10.0.0.12", host="hr-workstation-02",
                  groups=["insider", "privilege"],
                  raw_json={"rule_id": "40111", "level": 9}),
        ]
        for alert in alerts:
            db.add(alert)
        db.commit()

        # Cases WITHOUT AI fields
        now = datetime.now(timezone.utc)
        cases = [
            Case(id="IR-20260623-0001", title="SSH Brute Force on webserver01",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.unauthorized_access,
                 source_ip="203.0.113.42", source_host="webserver01",
                 alert_id="seed-alert-001",
                 detected_at=now - timedelta(hours=3)),
            Case(id="IR-20260623-0002", title="Phishing Attack on Finance Team",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.phishing,
                 source_ip="198.51.100.7", source_host="workstation-finance-03",
                 alert_id="seed-alert-002",
                 detected_at=now - timedelta(hours=1)),
            Case(id="IR-20260623-0003", title="Ransomware Detected on fileserver01",
                 severity=SeverityEnum.critical, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.ransomware,
                 source_ip=None, source_host="fileserver01",
                 alert_id="seed-alert-003",
                 detected_at=now - timedelta(hours=6)),
            Case(id="IR-20260623-0004", title="Suspected Data Exfiltration from DB Server",
                 severity=SeverityEnum.high, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.exfiltration,
                 source_ip="10.0.0.45", source_host="db-server-01",
                 alert_id="seed-alert-004",
                 detected_at=now - timedelta(minutes=45)),
            Case(id="IR-20260623-0005", title="Insider Access Anomaly — HR Workstation",
                 severity=SeverityEnum.medium, status=StatusEnum.open,
                 breach_type=BreachTypeEnum.insider,
                 source_ip="10.0.0.12", source_host="hr-workstation-02",
                 alert_id="seed-alert-005",
                 detected_at=now - timedelta(minutes=20)),
        ]
        for case in cases:
            db.add(case)
        db.commit()
        print("Seeded 5 cases WITHOUT AI fields.")
        print("Now call POST /cases/{id}/re-enrich on each case to trigger AI enrichment.")
        for c in cases:
            print(f"  curl -X POST http://localhost:8000/cases/{c.id}/re-enrich")
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    if "--no-ai" in sys.argv:
        seed_without_ai()
    else:
        seed()