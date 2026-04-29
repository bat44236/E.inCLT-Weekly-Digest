"""
send_digest.py - Emails the weekly_events.html digest
Reads HTML from file and sends as an HTML email.
"""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
EMAIL_FROM  = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASS  = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO    = os.getenv("EMAIL_TO", EMAIL_FROM)
HTML_PATH   = "weekly_events.html"

def get_week_label():
    today = datetime.today()
    sow   = today - timedelta(days=today.weekday())
    eow   = sow + timedelta(days=6)
    return f"{sow.strftime('%B %d')} - {eow.strftime('%B %d, %Y')}"

def main():
    print("=" * 60)
    print("  E.inCLT Digest Emailer")
    print("=" * 60)

    if not os.path.exists(HTML_PATH):
        print(f"❌ {HTML_PATH} not found — did digest_builder.py run?")
        raise FileNotFoundError(HTML_PATH)

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html_body = f.read()

    week_label = get_week_label()
    subject    = f"E.inCLT Weekly Digest — {week_label}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    print(f"\nSending to: {EMAIL_TO}")
    print(f"Subject: {subject}")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

    print("✅ Digest sent successfully!")

if __name__ == "__main__":
    main()
