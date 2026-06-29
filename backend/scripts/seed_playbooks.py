#!/usr/bin/env python3
# backend/scripts/seed_playbooks.py
"""
Seeds 5 production-quality playbooks covering all breach types.
Each playbook has 6-8 steps with exact Linux commands.
Usage: cd backend && python scripts/seed_playbooks.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.playbook import Playbook, PlaybookStep

PLAYBOOKS = [

    # ─── 1. RANSOMWARE ────────────────────────────────────────────────────────
    {
        "attack_type": "ransomware",
        "name": "Ransomware Response Playbook",
        "description": "Structured response for file-encrypting ransomware. Speed is critical — every minute of delay allows more files to be encrypted and increases recovery cost.",
        "steps": [
            {
                "step_number": 1,
                "title": "Isolate the infected host immediately",
                "description": "Disconnect the infected machine from the network to stop ransomware from spreading to shared drives, backup servers, and other hosts. Do NOT shut down the machine — RAM may contain decryption keys that forensics can recover.",
                "linux_cmd": "# On the infected Linux host:\nsudo ip link set eth0 down\n# OR physically unplug the network cable\n# Verify isolation:\nip addr show",
                "windows_cmd": "# Disable network adapter in Windows:\nDisable-NetAdapter -Name 'Ethernet' -Confirm:$false\n# Verify:\nGet-NetAdapter | Select Name, Status",
                "goal": "Stop lateral movement to other systems",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Preserve memory and disk evidence",
                "description": "Before any remediation, capture the system state. This is required for forensics and insurance claims. Use a USB drive or network share that is NOT connected to the infected machine.",
                "linux_cmd": "# Capture memory dump (requires LiME or avml):\nsudo avml /external-usb/memory_dump.lime\n\n# List running processes before shutdown:\nps aux > /external-usb/process_list.txt\nnetstat -tulpn > /external-usb/network_connections.txt\n\n# Note encrypted file extensions:\nfind /home /var /srv -name '*.enc' -o -name '*.locked' | head -50",
                "windows_cmd": "# Save process list:\nGet-Process | Export-Csv C:\\evidence\\processes.csv\nGet-NetTCPConnection | Export-Csv C:\\evidence\\connections.csv\n\n# Note ransom note location:\nGet-ChildItem C:\\ -Recurse -Filter 'READ_ME*' 2>$null | Select FullName",
                "goal": "Preserve forensic evidence before remediation",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Identify the ransomware strain",
                "description": "Identifying the specific strain determines whether a free decryptor exists. Upload a ransom note or encrypted file sample to ID Ransomware (https://id-ransomware.malwarehunterteam.com). Check No More Ransom (https://www.nomoreransom.org) for free decryptors before paying anything.",
                "linux_cmd": "# Check ransom note for strain indicators:\ncat /path/to/README_FOR_DECRYPT.txt\n\n# Check encrypted file extension:\nls /affected-directory/ | head -20\n\n# Check for known strain IOCs in logs:\ngrep -r 'ransom\\|encrypt\\|bitcoin' /var/log/ 2>/dev/null | tail -20",
                "windows_cmd": "# Find ransom notes:\nGet-ChildItem C:\\ -Recurse -Include 'README*','DECRYPT*','HOW_TO*' 2>$null\n\n# Check event logs for suspicious activity:\nGet-EventLog -LogName System -Newest 100 | Where-Object {$_.EntryType -eq 'Error'}",
                "goal": "Determine if a free decryptor exists before considering payment",
                "is_blocking": False
            },
            {
                "step_number": 4,
                "title": "Check and protect backups",
                "description": "Immediately verify your backups are clean and not encrypted. Ransomware specifically targets backup systems. Isolate clean backups from the network immediately.",
                "linux_cmd": "# Check backup server is reachable and clean:\nssh backup-server 'ls -lh /backups/ | tail -20'\n\n# Verify backup integrity (example with rsync):\nrsync --dry-run --checksum /backups/latest/ /tmp/verify/\n\n# Check if backup files show recent modification (sign of encryption):\nfind /backup-mount -newer /tmp/reference_file -type f | head -20",
                "windows_cmd": "# Check Windows Backup / Veeam status:\nGet-WBJob\n\n# List recent backup jobs:\nGet-WBBackupSet | Sort-Object BackupTime -Descending | Select -First 5",
                "goal": "Ensure clean backups exist for recovery",
                "is_blocking": True
            },
            {
                "step_number": 5,
                "title": "Notify management and legal",
                "description": "Under DPDP Act 2023, if personal data is affected, CERT-In must be notified within 6 hours of discovery. Notify your DPO, legal team, and senior management immediately. Do not communicate over email if email servers may be compromised — use phone.",
                "linux_cmd": "# Generate the DPDP breach notification from ZeroRespond:\ncurl -X POST http://localhost:8000/reports/<CASE_ID> \\\n  -H 'Authorization: Bearer <TOKEN>' \\\n  --output DPDP_Notification.pdf\n\n# Email to CERT-In: incident@cert-in.org.in\n# Subject: Cyber Security Incident Report — [Organisation Name]",
                "windows_cmd": "# Same curl command works from Windows PowerShell:\nInvoke-WebRequest -Uri 'http://localhost:8000/reports/<CASE_ID>' \\\n  -Headers @{Authorization='Bearer <TOKEN>'} \\\n  -OutFile DPDP_Notification.pdf",
                "goal": "Meet DPDP Act 2023 6-hour notification requirement",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Restore from clean backup",
                "description": "Once the infected system is isolated and evidence preserved, restore from the last known-clean backup. Rebuild the OS from scratch rather than restoring to the same infected system — ransomware may have persistence mechanisms.",
                "linux_cmd": "# Wipe and reinstall OS, then restore data:\n# 1. Boot from clean media\n# 2. Reinstall OS\n# 3. Restore data backup:\nrsync -avz --progress backup-server:/backups/pre-infection/ /restored-data/\n\n# Verify restored files:\nmd5sum /restored-data/critical-files/* > checksums.txt",
                "windows_cmd": "# Restore from backup:\nStart-WBFileRecovery -BackupSet (Get-WBBackupSet | Select -Last 1) \\\n  -FilePathToRestore 'C:\\Data' -RecoveryTarget 'D:\\Restored'",
                "goal": "Restore operations from clean backup",
                "is_blocking": True
            },
            {
                "step_number": 7,
                "title": "Post-incident hardening",
                "description": "After recovery, implement controls to prevent recurrence. Ransomware most commonly enters via unpatched systems, RDP exposed to internet, or phishing emails.",
                "linux_cmd": "# Update all packages:\nsudo apt update && sudo apt upgrade -y\n\n# Disable unused services:\nsudo systemctl disable telnet ftp rsh\n\n# Check for exposed RDP/SMB ports:\nss -tulpn | grep -E ':3389|:445|:139'\n\n# Enable automatic security updates:\nsudo dpkg-reconfigure -plow unattended-upgrades",
                "windows_cmd": "# Check Windows Update status:\nGet-WindowsUpdateLog\n\n# Disable RDP if not needed:\nSet-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name 'fDenyTSConnections' -Value 1\n\n# Enable Windows Defender:\nSet-MpPreference -DisableRealtimeMonitoring $false",
                "goal": "Prevent ransomware recurrence",
                "is_blocking": False
            }
        ]
    },

    # ─── 2. PHISHING ──────────────────────────────────────────────────────────
    {
        "attack_type": "phishing",
        "name": "Phishing Attack Response Playbook",
        "description": "Response for phishing attacks including credential harvesting, malicious links, and email-delivered malware. Focus on containing the blast radius and preventing credential reuse.",
        "steps": [
            {
                "step_number": 1,
                "title": "Identify affected users and scope",
                "description": "Determine who received the phishing email, who clicked the link, and who may have entered credentials. Pull mail server logs immediately — email logs are often overwritten within 24-72 hours.",
                "linux_cmd": "# Pull mail server logs (Postfix example):\ngrep 'phishing-domain.com' /var/log/mail.log | grep 'delivered'\n\n# Check web proxy logs for clicks on malicious URL:\ngrep 'malicious-url.com' /var/log/squid/access.log\n\n# List all users who accessed the malicious URL:\nawk '{print $8}' /var/log/squid/access.log | grep 'malicious' | sort | uniq",
                "windows_cmd": "# Search Exchange mail logs:\nGet-MessageTrackingLog -ResultSize Unlimited -MessageSubject 'phishing subject' | Select Sender, Recipients, Timestamp\n\n# Search for URL clicks in Exchange:\nGet-MessageTrackingLog -EventId DELIVER | Where-Object {$_.Recipients -like '*finance*'}",
                "goal": "Know exactly who was targeted and who interacted with the phishing content",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Block the malicious URL and sender domain",
                "description": "Immediately block the phishing URL and sender domain at the email gateway and web proxy. This stops anyone else in the organisation from clicking the link.",
                "linux_cmd": "# Block domain at DNS level (add to /etc/hosts on DNS server or Pi-hole):\necho '0.0.0.0 malicious-domain.com' | sudo tee -a /etc/hosts\n\n# Block in UFW firewall:\nsudo ufw deny out to any port 80,443 comment 'block phishing domain'\n\n# Add to email blacklist (Postfix):\necho 'malicious-sender@phishing.com REJECT Phishing attempt' >> /etc/postfix/sender_access\npostmap /etc/postfix/sender_access\nsudo systemctl reload postfix",
                "windows_cmd": "# Block URL in Windows Defender SmartScreen or proxy:\nAdd-MpPreference -ExclusionPath 'N/A'  # Use Windows Firewall\nNew-NetFirewallRule -DisplayName 'Block Phishing' -Direction Outbound -Action Block -RemoteAddress 'phishing-ip'",
                "goal": "Prevent further exposure across the organisation",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Force password reset for all affected users",
                "description": "Any user who may have entered credentials on the phishing page must reset their password immediately. Also revoke all active sessions for those accounts.",
                "linux_cmd": "# Force password change on next login (Linux/LDAP):\npasswd -e username\n\n# For multiple users from a file:\nwhile read user; do passwd -e \"$user\"; done < affected_users.txt\n\n# Revoke SSH keys if compromised:\nrm /home/username/.ssh/authorized_keys\n\n# Check for new SSH keys added by attacker:\nfind /home -name 'authorized_keys' -newer /tmp/reference_date -ls",
                "windows_cmd": "# Force password reset in Active Directory:\nSet-ADUser -Identity 'username' -ChangePasswordAtLogon $true\n\n# Revoke all active sessions:\nRevoke-MgUserSignInSession -UserId 'user@domain.com'\n\n# Bulk reset from list:\nGet-Content affected_users.txt | ForEach-Object { Set-ADUser $_ -ChangePasswordAtLogon $true }",
                "goal": "Neutralise harvested credentials before attackers use them",
                "is_blocking": True
            },
            {
                "step_number": 4,
                "title": "Check for account compromise and lateral movement",
                "description": "Review authentication logs for the affected accounts. Look for logins from unusual IPs, at unusual times, or to systems they do not normally access.",
                "linux_cmd": "# Check auth logs for suspicious logins:\ngrep 'Accepted password' /var/log/auth.log | grep 'username'\n\n# Look for logins from foreign IPs:\ngrep 'Accepted' /var/log/auth.log | awk '{print $11}' | sort | uniq -c | sort -rn\n\n# Check for privilege escalation attempts:\ngrep 'sudo\\|su ' /var/log/auth.log | grep 'username'",
                "windows_cmd": "# Check Windows event logs for suspicious logons (Event ID 4624):\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} | Where-Object {$_.Message -like '*username*'} | Select TimeCreated, Message | Select -First 20\n\n# Look for logons from unusual locations:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4625} | Select -First 50",
                "goal": "Determine if attacker already used the harvested credentials",
                "is_blocking": False
            },
            {
                "step_number": 5,
                "title": "Enable MFA for all affected accounts",
                "description": "Password reset alone is not enough if the attacker still has the old password. Enable multi-factor authentication on all affected accounts before they log back in.",
                "linux_cmd": "# Enable Google Authenticator for SSH (PAM):\nsudo apt install libpam-google-authenticator\n\n# Configure PAM:\necho 'auth required pam_google_authenticator.so' | sudo tee -a /etc/pam.d/sshd\n\n# Update SSH config:\necho 'ChallengeResponseAuthentication yes' | sudo tee -a /etc/ssh/sshd_config\nsudo systemctl restart sshd",
                "windows_cmd": "# Enable MFA via Microsoft 365 / Azure AD:\nSet-MsolUser -UserPrincipalName 'user@domain.com' -StrongAuthenticationRequirements @(New-Object -TypeName Microsoft.Online.Administration.StrongAuthenticationRequirement)",
                "goal": "Prevent future credential reuse even if attacker retains the password",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Report phishing email to CERT-In and conduct user awareness",
                "description": "Report the phishing campaign to CERT-In (incident@cert-in.org.in) with the full email headers and malicious URL. Run an immediate awareness session with staff about the specific phishing technique used.",
                "linux_cmd": "# Generate DPDP report:\ncurl -X POST http://localhost:8000/reports/<CASE_ID> \\\n  -H 'Authorization: Bearer <TOKEN>' \\\n  --output DPDP_Phishing_Report.pdf\n\n# Save full email headers for CERT-In submission:\ncat /var/mail/username | head -100 > phishing_email_headers.txt",
                "windows_cmd": "# Export phishing email from Outlook:\n# File > Open & Export > Import/Export > Export to a File > Outlook Data File (.pst)",
                "goal": "Meet reporting obligations and prevent recurrence",
                "is_blocking": False
            }
        ]
    },

    # ─── 3. UNAUTHORIZED ACCESS ───────────────────────────────────────────────
    {
        "attack_type": "unauthorized_access",
        "name": "Unauthorised Access Response Playbook",
        "description": "Response for brute force attacks, authentication bypass, and unauthorised login attempts. Focus on blocking the attacker, assessing damage, and hardening access controls.",
        "steps": [
            {
                "step_number": 1,
                "title": "Block the attacking IP immediately",
                "description": "Block the source IP at the firewall and on the affected host. If the attacker is using multiple IPs (distributed brute force), block the entire subnet.",
                "linux_cmd": "# Block single IP:\nsudo ufw deny from 203.0.113.42 to any\n# OR with iptables:\nsudo iptables -A INPUT -s 203.0.113.42 -j DROP\n\n# Block entire subnet if distributed attack:\nsudo ufw deny from 203.0.113.0/24 to any\n\n# Verify block:\nsudo ufw status numbered\n\n# Install and use fail2ban for automatic blocking:\nsudo apt install fail2ban\nsudo systemctl enable fail2ban --now",
                "windows_cmd": "# Block IP in Windows Firewall:\nNew-NetFirewallRule -DisplayName 'Block Attacker' -Direction Inbound -Action Block -RemoteAddress '203.0.113.42'\n\n# Verify:\nGet-NetFirewallRule -DisplayName 'Block Attacker'",
                "goal": "Stop the ongoing attack immediately",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Determine if any login was successful",
                "description": "A brute force attack is low impact if no login succeeded. Check authentication logs very carefully for any 'Accepted' entries from the attacking IP before the block took effect.",
                "linux_cmd": "# Check for successful logins from the attacker IP:\ngrep 'Accepted' /var/log/auth.log | grep '203.0.113.42'\n\n# Check all successful logins in the attack window:\ngrep 'Accepted password\\|Accepted publickey' /var/log/auth.log | \\\n  awk '{print $1, $2, $3, $9, $11}'\n\n# Check for any new users created recently (attacker persistence):\ngrep 'new user\\|useradd\\|adduser' /var/log/auth.log\nawk -F: '$3 > 1000 {print $1, $3}' /etc/passwd",
                "windows_cmd": "# Search for successful logons from attacking IP:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} | \\\n  Where-Object {$_.Message -like '*203.0.113.42*'} | Select TimeCreated, Message\n\n# Check for new accounts created:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4720} | Select -First 10",
                "goal": "Determine if the attacker gained access — this changes the severity of the response",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Review and strengthen password policy",
                "description": "Brute force succeeds because of weak passwords. Check what accounts were targeted and enforce stronger passwords immediately.",
                "linux_cmd": "# Install and configure password quality checking:\nsudo apt install libpam-pwquality\n\n# Configure /etc/security/pwquality.conf:\nminlen = 12\ndcredit = -1\nucredit = -1\nocredit = -1\nlcredit = -1\n\n# Check accounts with empty or no password:\nsudo awk -F: '($2 == \"\" || $2 == \"!\") {print $1}' /etc/shadow\n\n# Check for accounts with no password expiry:\nsudo chage -l username",
                "windows_cmd": "# Set password policy via Group Policy or local policy:\nnet accounts /minpwlen:12 /maxpwage:90 /uniquepw:5\n\n# Check current password policy:\nnet accounts",
                "goal": "Close the vulnerability that allowed the brute force attempt",
                "is_blocking": False
            },
            {
                "step_number": 4,
                "title": "Restrict SSH / RDP to known IPs only",
                "description": "SSH and RDP should never be open to the entire internet. Restrict access to specific IP ranges or implement a VPN for remote access.",
                "linux_cmd": "# Restrict SSH to specific IPs only:\nsudo ufw allow from 10.0.0.0/8 to any port 22\nsudo ufw allow from 192.168.0.0/16 to any port 22\nsudo ufw deny 22\n\n# Change SSH to non-standard port:\nsudo sed -i 's/#Port 22/Port 2222/' /etc/ssh/sshd_config\nsudo systemctl restart sshd\n\n# Disable password auth — use keys only:\nsudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config",
                "windows_cmd": "# Restrict RDP to internal network only:\nNew-NetFirewallRule -DisplayName 'RDP Internal Only' -Direction Inbound -LocalPort 3389 -Protocol TCP -RemoteAddress '10.0.0.0/8' -Action Allow\nNew-NetFirewallRule -DisplayName 'Block RDP External' -Direction Inbound -LocalPort 3389 -Protocol TCP -Action Block",
                "goal": "Prevent future brute force from the internet",
                "is_blocking": False
            },
            {
                "step_number": 5,
                "title": "Configure automatic blocking with fail2ban",
                "description": "Fail2ban monitors auth logs and automatically blocks IPs after a configurable number of failed attempts. This provides ongoing protection without manual intervention.",
                "linux_cmd": "# Install fail2ban:\nsudo apt install fail2ban -y\n\n# Create local config:\nsudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local\n\n# Configure SSH jail in /etc/fail2ban/jail.local:\n[sshd]\nenabled = true\nport    = ssh\nfilter  = sshd\nlogpath = /var/log/auth.log\nmaxretry = 5\nbantime  = 3600\nfindtime = 600\n\n# Start and enable:\nsudo systemctl enable fail2ban --now\n\n# Check status:\nsudo fail2ban-client status sshd",
                "windows_cmd": "# Windows equivalent: configure Account Lockout Policy:\nnet accounts /lockoutthreshold:5 /lockoutduration:60 /lockoutwindow:10\n\n# Or use Windows Defender ATP for automatic blocking",
                "goal": "Automate protection against future brute force attempts",
                "is_blocking": False
            },
            {
                "step_number": 6,
                "title": "Enable two-factor authentication",
                "description": "Even if an attacker gets a valid password, 2FA stops them from logging in. Enable it on all internet-facing services.",
                "linux_cmd": "# Install Google Authenticator PAM module:\nsudo apt install libpam-google-authenticator -y\n\n# Run as each user to set up:\ngoogle-authenticator\n\n# Configure PAM for SSH:\necho 'auth required pam_google_authenticator.so' | sudo tee -a /etc/pam.d/sshd\necho 'AuthenticationMethods publickey,keyboard-interactive' | sudo tee -a /etc/ssh/sshd_config\nsudo systemctl restart sshd",
                "windows_cmd": "# Enable Azure MFA for all users:\nConnect-MsolService\nGet-MsolUser -All | Where-Object {$_.IsLicensed -eq $true} | ForEach-Object {\n  $Requirements = @()\n  $Requirements += New-Object -TypeName Microsoft.Online.Administration.StrongAuthenticationRequirement\n  Set-MsolUser -UserPrincipalName $_.UserPrincipalName -StrongAuthenticationRequirements $Requirements\n}",
                "goal": "Make stolen passwords useless without a second factor",
                "is_blocking": False
            }
        ]
    },

    # ─── 4. EXFILTRATION ──────────────────────────────────────────────────────
    {
        "attack_type": "exfiltration",
        "name": "Data Exfiltration Response Playbook",
        "description": "Response for suspected or confirmed data theft. Focus on stopping the transfer, determining what data left, and meeting DPDP Act 2023 notification requirements.",
        "steps": [
            {
                "step_number": 1,
                "title": "Block the outbound connection immediately",
                "description": "Stop the active data transfer. Block the destination IP and the source host's outbound internet access while preserving the system for forensics.",
                "linux_cmd": "# Block outbound to exfiltration destination:\nsudo ufw deny out to <destination-ip>\n\n# Block all outbound from the compromised host (drastic but effective):\nsudo iptables -I OUTPUT -j DROP\n\n# Capture the active connection before blocking:\nsudo ss -tulpn | grep ESTABLISHED\nsudo netstat -anp | grep '<destination-ip>' > /evidence/active_connections.txt\n\n# Capture network traffic dump:\nsudo tcpdump -i eth0 -w /evidence/capture.pcap host <destination-ip> &",
                "windows_cmd": "# Block outbound connection:\nNew-NetFirewallRule -DisplayName 'Block Exfil' -Direction Outbound -Action Block -RemoteAddress '<destination-ip>'\n\n# Capture traffic:\nnetsh trace start capture=yes tracefile=C:\\evidence\\capture.etl",
                "goal": "Stop data leaving the network immediately",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Quantify what data was transferred",
                "description": "Determine how much data left, to where, and what it may have contained. This is critical for DPDP reporting — you must estimate the number of persons affected.",
                "linux_cmd": "# Check network traffic volume to destination IP (from NetFlow or proxy logs):\ngrep '<destination-ip>' /var/log/squid/access.log | \\\n  awk '{sum += $5} END {print \"Total bytes transferred: \" sum}'\n\n# Check what files were recently accessed on the compromised host:\nfind /sensitive-data -type f -newer /tmp/reference_file -ls\n\n# Check database query logs:\ngrep 'SELECT.*FROM' /var/log/postgresql/postgresql.log | tail -100\n\n# Review bash history of compromised user:\ncat /home/username/.bash_history | grep -E 'curl|wget|scp|rsync|tar'",
                "windows_cmd": "# Check recent file access:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} | Select -First 50\n\n# Check PowerShell history:\nGet-Content (Get-PSReadlineOption).HistorySavePath | Select-String 'Invoke-WebRequest|curl|ftp'",
                "goal": "Establish what personal data may have been exfiltrated for DPDP reporting",
                "is_blocking": True
            },
            {
                "step_number": 3,
                "title": "Identify and contain the exfiltration vector",
                "description": "Determine how data was being exfiltrated — web upload, email attachment, FTP, cloud sync, or physical media — and close that channel.",
                "linux_cmd": "# Check for active cloud sync clients:\nps aux | grep -E 'dropbox|onedrive|googledrive|rclone|rsync'\n\n# Check for scheduled tasks that may be exfiltrating data:\ncrontab -l\nsudo cat /etc/cron*\n\n# Check for unauthorised tools installed:\nwhich ncat nc socat curl wget | xargs ls -la\nfind / -name 'rclone' -o -name 'exfil*' 2>/dev/null\n\n# Check recently installed packages:\ndpkg --get-selections | grep -v deinstall | tail -20",
                "windows_cmd": "# Check for cloud sync:\nGet-Process | Where-Object {$_.Name -like '*drop*' -or $_.Name -like '*one*'}\n\n# Check scheduled tasks:\nGet-ScheduledTask | Where-Object {$_.State -eq 'Ready'} | Select TaskName, TaskPath",
                "goal": "Close the exfiltration channel and remove attacker tools",
                "is_blocking": True
            },
            {
                "step_number": 4,
                "title": "Determine root cause of compromise",
                "description": "How did the attacker get access to the system that was exfiltrating data? Look for the initial access vector — phishing email, compromised credential, unpatched vulnerability, or insider.",
                "linux_cmd": "# Review authentication logs for the days before exfiltration:\ngrep 'Accepted' /var/log/auth.log | grep -v 'known-good-ip'\n\n# Check for webshell or backdoor:\nfind /var/www -type f -name '*.php' -newer /tmp/reference_date\ngrep -r 'eval(base64_decode' /var/www/ 2>/dev/null\n\n# Check for new cron jobs or systemd services:\nls -la /etc/cron.d/ /etc/systemd/system/*.service | grep -v 'root'\n\n# Look for recently modified system files:\nfind /etc /bin /usr/bin -newer /tmp/reference_date -type f",
                "windows_cmd": "# Check for recently installed software:\nGet-WmiObject Win32_Product | Sort-Object InstallDate -Descending | Select -First 10\n\n# Review PowerShell execution logs:\nGet-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-PowerShell/Operational'} | Select -First 50",
                "goal": "Understand how the attacker got in so you can close the initial access vector",
                "is_blocking": False
            },
            {
                "step_number": 5,
                "title": "Notify affected data principals and CERT-In",
                "description": "Under DPDP Act 2023, data principals (the people whose data was stolen) must be notified. CERT-In must be notified within 6 hours. Generate the breach notification report and contact affected individuals.",
                "linux_cmd": "# Generate DPDP breach notification:\ncurl -X POST http://localhost:8000/reports/<CASE_ID> \\\n  -H 'Authorization: Bearer <TOKEN>' \\\n  --output DPDP_Exfiltration_Report.pdf\n\n# Email CERT-In:\n# To: incident@cert-in.org.in\n# Subject: Data Breach Notification — [Organisation] — [Date]\n# Attach: DPDP_Exfiltration_Report.pdf",
                "windows_cmd": "# Same API call from PowerShell:\nInvoke-WebRequest -Uri 'http://localhost:8000/reports/<CASE_ID>' \\\n  -Headers @{Authorization='Bearer <TOKEN>'} -Method POST \\\n  -OutFile DPDP_Exfiltration_Report.pdf",
                "goal": "Meet DPDP Act 2023 mandatory notification requirements",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Implement DLP controls",
                "description": "After the incident is contained, implement Data Loss Prevention controls to monitor and block unauthorised data transfers in future.",
                "linux_cmd": "# Monitor outbound data with OpenDLP or similar:\n# Configure network monitoring on the gateway:\nsudo apt install nload iftop nethogs -y\n\n# Set up egress filtering rules:\n# Only allow outbound on specific ports and destinations\nsudo ufw default deny outgoing\nsudo ufw allow out 80/tcp\nsudo ufw allow out 443/tcp\nsudo ufw allow out 53/udp\n\n# Log all outbound connections:\nsudo ufw logging on",
                "windows_cmd": "# Enable Windows Information Protection:\n# Configure via Intune or Group Policy\n\n# Monitor outbound with Windows Firewall logging:\nnetsh advfirewall set global statefulftp disable\nnetsh advfirewall set currentprofile logging filename C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log",
                "goal": "Prevent future exfiltration with ongoing monitoring",
                "is_blocking": False
            }
        ]
    },

    # ─── 5. INSIDER ───────────────────────────────────────────────────────────
    {
        "attack_type": "insider",
        "name": "Insider Threat Response Playbook",
        "description": "Response for suspected insider threats — employees or contractors misusing access. Requires careful handling to avoid tipping off the suspect while preserving evidence for HR and legal proceedings.",
        "steps": [
            {
                "step_number": 1,
                "title": "Preserve evidence quietly — do not alert the suspect",
                "description": "Unlike external attacks, insider investigations require discretion. Preserve all evidence before taking any action that the suspect might notice. Contact HR and legal before doing anything visible to the employee.",
                "linux_cmd": "# Quietly capture logs without the user knowing:\n# Copy relevant auth logs to secure location:\nsudo cp /var/log/auth.log /secure-evidence/auth_$(date +%Y%m%d).log\n\n# Capture user's recent activity without logging in as them:\nsudo last username > /secure-evidence/login_history.txt\nsudo lastb username >> /secure-evidence/failed_logins.txt\n\n# Export user's process history (non-intrusively):\nsudo ausearch -ua $(id -u username) > /secure-evidence/audit_trail.txt",
                "windows_cmd": "# Export event logs for the user silently:\nGet-WinEvent -FilterHashtable @{LogName='Security'} | \\\n  Where-Object {$_.Message -like '*username*'} | \\\n  Export-Csv C:\\SecureEvidence\\user_events.csv -NoTypeInformation\n\n# Export file access logs:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} | \\\n  Where-Object {$_.Message -like '*username*'} | Select -First 100",
                "goal": "Gather evidence without alerting the suspect and allowing evidence destruction",
                "is_blocking": True
            },
            {
                "step_number": 2,
                "title": "Establish the timeline of suspicious activity",
                "description": "Build a complete timeline of what the user accessed, when, from where, and what they did. This is the foundation of any HR or legal action.",
                "linux_cmd": "# Build access timeline:\ngrep 'username' /var/log/auth.log | grep -E 'Accepted|session opened|session closed' | \\\n  awk '{print $1, $2, $3, $NF}' | sort > /secure-evidence/timeline.txt\n\n# Check file access times (if audit logging is enabled):\nausearch -ua $(id -u username) -ts 2026-01-01 -te today | aureport --file\n\n# Check database access:\ngrep 'username' /var/log/postgresql/postgresql.log | grep -E 'SELECT|INSERT|DELETE|UPDATE' | \\\n  grep -v 'pg_' > /secure-evidence/db_queries.txt\n\n# Check VPN/remote access logs:\ngrep 'username' /var/log/openvpn.log",
                "windows_cmd": "# Build Windows timeline:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4624,4634,4663,4688} | \\\n  Where-Object {$_.Message -like '*username*'} | \\\n  Sort-Object TimeCreated | Export-Csv timeline.csv",
                "goal": "Create a legally admissible activity timeline",
                "is_blocking": False
            },
            {
                "step_number": 3,
                "title": "Identify what data was accessed or copied",
                "description": "Determine exactly what sensitive data the insider accessed, modified, or copied. Pay special attention to bulk downloads, data exports, and access to data outside their normal role.",
                "linux_cmd": "# Check files accessed outside normal work hours:\nausearch -ua $(id -u username) -ts 2026-01-01T00:00:00 -te 2026-01-01T07:00:00 | \\\n  aureport --file | grep 'read\\|open'\n\n# Check for large file copies or downloads:\nfind /home/username /tmp -type f -newer /tmp/reference_date -size +10M -ls\n\n# Check email sent (if sendmail/postfix logs are available):\ngrep 'username@domain' /var/log/mail.log | grep 'status=sent'\n\n# Check USB device usage:\ngrep -i 'usb\\|removable' /var/log/syslog | tail -50",
                "windows_cmd": "# Check file access for the user:\nGet-WinEvent -FilterHashtable @{LogName='Security'; Id=4663} | \\\n  Where-Object {$_.Message -like '*username*' -and $_.Message -like '*sensitive*'} | Select -First 50\n\n# Check for USB device connections:\nGet-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-DriverFrameworks-UserMode/Operational'; Id=2003} | Select -First 10",
                "goal": "Establish what data was compromised and determine DPDP notification obligation",
                "is_blocking": False
            },
            {
                "step_number": 4,
                "title": "Involve HR and legal before taking action",
                "description": "Do NOT suspend the account, confront the employee, or take disciplinary action without HR and legal approval. Premature action can compromise legal proceedings and expose the organisation to wrongful termination claims.",
                "linux_cmd": "# Document your findings clearly:\ncat > /secure-evidence/summary_for_hr.txt << EOF\nDate of discovery: $(date)\nEmployee: [name]\nSuspicious activity: [describe]\nTime period: [start] to [end]\nData potentially accessed: [list]\nEvidence location: /secure-evidence/\nEOF\n\n# Do not take any system action until HR/legal approve\necho 'WAITING FOR HR AND LEGAL APPROVAL BEFORE PROCEEDING'",
                "windows_cmd": "# Same — document findings and wait for HR/legal\n# Do not lock the account yet\n# Do not confront the employee",
                "goal": "Ensure legally sound process that protects the organisation",
                "is_blocking": True
            },
            {
                "step_number": 5,
                "title": "Revoke access and contain (after HR approval)",
                "description": "Only after HR and legal have reviewed the evidence and approved action: disable the account, revoke all access credentials, and collect the employee's devices.",
                "linux_cmd": "# Disable user account (after HR approval):\nsudo usermod -L username   # Lock account\nsudo usermod -s /usr/sbin/nologin username   # Disable shell\n\n# Revoke SSH keys:\nsudo mv /home/username/.ssh/authorized_keys /secure-evidence/revoked_keys_username\n\n# Remove from sudo group:\nsudo gpasswd -d username sudo\n\n# Expire all active sessions:\nsudo pkill -u username\n\n# Change shared passwords the user knew:\n# (document which shared passwords need rotation)",
                "windows_cmd": "# Disable AD account (after HR approval):\nDisable-ADAccount -Identity 'username'\n\n# Reset password immediately:\nSet-ADAccountPassword -Identity 'username' -Reset -NewPassword (ConvertTo-SecureString 'TempPass@123!' -AsPlainText -Force)\n\n# Revoke all active sessions:\nRevoke-MgUserSignInSession -UserId 'user@domain.com'",
                "goal": "Remove access without tipping off prematurely",
                "is_blocking": True
            },
            {
                "step_number": 6,
                "title": "Review and tighten access controls",
                "description": "After the incident, conduct a least-privilege audit. Employees should only have access to data required for their specific role. Remove accumulated permissions that were granted over time but are no longer needed.",
                "linux_cmd": "# Audit all users with elevated permissions:\nsudo grep -E '^sudo:|^admin:' /etc/group\ncat /etc/sudoers\n\n# List all users who can SSH to this server:\ncat /etc/ssh/sshd_config | grep 'AllowUsers\\|AllowGroups'\n\n# Review all files accessible to user's group:\nfind / -group groupname -type f 2>/dev/null | head -50\n\n# Implement mandatory access control (AppArmor/SELinux):\nsudo apt install apparmor-utils\nsudo aa-status",
                "windows_cmd": "# Audit all users in privileged groups:\nGet-ADGroupMember -Identity 'Domain Admins' | Select Name, SamAccountName\nGet-ADGroupMember -Identity 'Administrators' | Select Name\n\n# Review user permissions on sensitive folders:\nGet-Acl 'C:\\SensitiveData' | Format-List",
                "goal": "Implement least-privilege to reduce insider threat exposure",
                "is_blocking": False
            }
        ]
    }
]


def seed_playbooks():
    db = SessionLocal()
    try:
        # Clear existing playbooks
        db.query(PlaybookStep).delete()
        db.query(Playbook).delete()
        db.commit()
        print("Cleared existing playbooks.")

        total_steps = 0
        for pb_data in PLAYBOOKS:
            steps_data = pb_data.pop("steps")

            playbook = Playbook(
                attack_type=pb_data["attack_type"],
                name=pb_data["name"],
                description=pb_data["description"]
            )
            db.add(playbook)
            db.flush()   # Get the playbook ID

            for step_data in steps_data:
                step = PlaybookStep(playbook_id=playbook.id, **step_data)
                db.add(step)
                total_steps += 1

            print(f"  ✓ {playbook.name} ({len(steps_data)} steps)")

        db.commit()
        print(f"\nSeeded {len(PLAYBOOKS)} playbooks with {total_steps} steps total.")
        print("\nVerify with:")
        print("  curl http://localhost:8000/playbooks -H 'Authorization: Bearer <TOKEN>'")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_playbooks()