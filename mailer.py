"""
mailer.py

Sends emails via Gmail SMTP (App Password auth) — staff notifications on
new enquiries, customer confirmations using email_templates.py, and
internal alert emails when something breaks (paired with monitoring.py).

Requires these Render environment variables (same ones you already have):
  EMAIL_USER   - Gmail address sending the emails
  EMAIL_PASS   - Gmail App Password
  STAFF_EMAIL  - where staff notifications and alerts go
"""

import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from email_templates import build_confirmation_email

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _send(to_addr: str, subject: str, html_body: str = None, text_body: str = None) -> bool:
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    if not email_user or not email_pass:
        print("❌ [MAILER] EMAIL_USER/EMAIL_PASS not configured", flush=True)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = to_addr

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(email_user, email_pass)
            server.sendmail(email_user, to_addr, msg.as_string())
        return True
    except Exception as e:
        print(f"❌ [MAILER] Failed to send to {to_addr}: {e}", flush=True)
        return False


def send_customer_confirmation(customer_data: dict, resolved_items: list = None, enquiry_id: int = None) -> bool:
    to_addr = customer_data.get("email")
    if not to_addr:
        print("⚠️ [MAILER] No customer email provided, skipping confirmation", flush=True)
        return False
    subject, html_body, text_body = build_confirmation_email(customer_data, resolved_items, enquiry_id)
    return _send(to_addr, subject, html_body, text_body)


def send_staff_notification(customer_data: dict, resolved_items: list = None) -> bool:
    staff_email = os.getenv("STAFF_EMAIL")
    if not staff_email:
        print("❌ [MAILER] STAFF_EMAIL not configured", flush=True)
        return False

    items = resolved_items or []
    if items:
        parts_summary = "\n".join(
            f"- {it['name']} (OEM: {it.get('oem', 'N/A')}) — £{float(it.get('price', 0)):.2f}"
            for it in items
        )
    else:
        parts_summary = customer_data.get("part", "N/A")

    subject = f"New enquiry: {customer_data.get('name', 'Unknown')} - {customer_data.get('vehicle', '')}"
    text_body = f"""New enquiry received:

Name: {customer_data.get('name', 'N/A')}
Phone: {customer_data.get('phone', 'N/A')}
Email: {customer_data.get('email', 'N/A')}
Vehicle: {customer_data.get('vehicle', 'N/A')}

Parts:
{parts_summary}
"""
    return _send(staff_email, subject, text_body=text_body)


def alert_staff(subject: str, message: str) -> bool:
    """Internal error alerts — see monitoring.py for the cooldown logic that
    stops this from spamming your inbox during an extended outage."""
    staff_email = os.getenv("STAFF_EMAIL")
    if not staff_email:
        print(f"❌ [MAILER] STAFF_EMAIL not configured, cannot send alert: {subject}", flush=True)
        return False
    return _send(staff_email, f"[Chatbot Alert] {subject}", text_body=message)


def send_backup_email(file_path: str, size_mb: float) -> bool:
    """Emails a database backup file as an attachment. Uses BACKUP_EMAIL if
    set (recommended — a separate inbox/folder keeps backups from cluttering
    day-to-day staff notifications), otherwise falls back to STAFF_EMAIL."""
    backup_email = os.getenv("BACKUP_EMAIL") or os.getenv("STAFF_EMAIL")
    if not backup_email:
        print("❌ [MAILER] No BACKUP_EMAIL or STAFF_EMAIL configured, cannot send backup", flush=True)
        return False

    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    if not email_user or not email_pass:
        print("❌ [MAILER] EMAIL_USER/EMAIL_PASS not configured", flush=True)
        return False

    date_str = time.strftime("%Y-%m-%d")
    msg = MIMEMultipart()
    msg["Subject"] = f"Cherrywood DB Backup - {date_str} ({size_mb:.2f} MB)"
    msg["From"] = email_user
    msg["To"] = backup_email
    msg.attach(MIMEText(
        f"Automatic daily database backup attached.\nSize: {size_mb:.2f} MB\nDate: {date_str}",
        "plain"
    ))

    try:
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="inventory_backup_{date_str}.db"')
        msg.attach(part)

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(email_user, email_pass)
            server.sendmail(email_user, backup_email, msg.as_string())
        return True
    except Exception as e:
        print(f"❌ [MAILER] Failed to send backup email: {e}", flush=True)
        return False
