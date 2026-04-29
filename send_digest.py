"""
send_digest.py - Emails the weekly_events.html digest
Attaches header_image.png as an inline CID attachment so email clients render it correctly.
"""

import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

SMTP_SERVER    = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
EMAIL_FROM     = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASS     = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO       = os.getenv("EMAIL_TO", EMAIL_FROM)
HTML_PATH      = "weekly_events.html"
IMAGE_PATH     = "header_image.png"

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

    # If the header image exists, swap the base64 src for a CID reference
    # so it travels as a proper inline attachment instead of a huge data URI
    has_image = os.path.exists(IMAGE_PATH)
    if has_image:
        html_body = re.sub(
            r'src="data:image/png;base64,[^"]+"',
            'src="cid:header_image"',
            html_body,
            count=1
        )

    week_label = get_week_label()
    subject    = f"E.inCLT Weekly Digest — {week_label}"

    # Build the email
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    # Attach HTML body
    msg.attach(MIMEText(html_body, "html"))

    # Attach header image as inline CID attachment
    if has_image:
        with open(IMAGE_PATH, "rb") as img_file:
            img = MIMEImage(img_file.read(), _subtype="png")
        img.add_header("Content-ID", "<header_image>")
        img.add_header("Content-Disposition", "inline", filename="header_image.png")
        msg.attach(img)
        print(f"     Header image attached as inline CID")
    else:
        print(f"     ⚠️  {IMAGE_PATH} not found — sending without header image")

    print(f"\nSending to: {EMAIL_TO}")
    print(f"Subject: {subject}")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

    print("✅ Digest sent successfully!")

if __name__ == "__main__":
    main()
