"""Email today's digest.html with the CV PDFs attached (Gmail SMTP)."""
import datetime
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

out_dir = Path(__file__).parent / "out" / datetime.date.today().isoformat()
digest = out_dir / "digest.html"
if not digest.exists():
    raise SystemExit("no digest today")

pdfs = sorted(out_dir.glob("*.pdf"))
msg = EmailMessage()
msg["Subject"] = f"Job digest {out_dir.name}: {len(pdfs)} CVs"
msg["From"] = os.environ["GMAIL_USER"]
msg["To"] = os.environ.get("DIGEST_TO") or os.environ["GMAIL_USER"]
msg.set_content("Open this email in an HTML-capable client.")
msg.add_alternative(digest.read_text(encoding="utf-8"), subtype="html")
for pdf in pdfs:
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    s.send_message(msg)
print(f"sent digest with {len(pdfs)} CVs")
