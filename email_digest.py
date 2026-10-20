"""Email a person's digest.html for today with the CV PDFs attached (Gmail SMTP)."""
import datetime
import os
import smtplib
import sys
from email.message import EmailMessage

import person

cfg, _ = person.load(sys.argv[1])
out_dir = person.ROOT / "out" / sys.argv[1] / datetime.date.today().isoformat()
digest = out_dir / "digest.html"
if not digest.exists():
    raise SystemExit("no digest today")

pdfs = sorted(out_dir.glob("*.pdf"))
msg = EmailMessage()
msg["Subject"] = f"Job digest {out_dir.name}: {len(pdfs)} CVs"
msg["From"] = os.environ["GMAIL_USER"]
msg["To"] = cfg.get("email_to") or cfg["contact"]["email"]
msg.set_content("Open this email in an HTML-capable client.")
msg.add_alternative(digest.read_text(encoding="utf-8"), subtype="html")
for pdf in pdfs:
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    s.send_message(msg)
print(f"sent digest with {len(pdfs)} CVs")
