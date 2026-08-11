"""POC: send ONE test notification email. Prefers the Resend API when a key is set, else SMTP.

Standalone, dependency-free (stdlib only) — proves the mail path works before we wire it into
the scheduler. Config comes from the environment (populate .env; it is gitignored and never
committed). Secrets are read from env and NEVER printed/logged.

Env (see .env.example):
  RESUMAKER_RESEND_API_KEY  if set -> send via Resend API (recommended: send-only key)
  RESUMAKER_SMTP_HOST/PORT/USER/PASS  else -> send via SMTP (e.g. Gmail App Password)
  RESUMAKER_NOTIFY_TO       recipient (Resend free tier w/o a verified domain: your account email)
  RESUMAKER_NOTIFY_FROM     optional; Resend defaults to onboarding@resend.dev, SMTP to USER

Run (loads .env into the process for this command only):
  uv run --env-file .env python pocs/notify/send_test.py
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

SUBJECT = "resumaker — mailer POC ✅"
TEXT = "resumaker mailer POC — the mail path is wired correctly."
HTML = ("<div style='font-family:system-ui,sans-serif'>"
        "<h2 style='margin:0 0 8px'>resumaker mailer works ✅</h2>"
        "<p style='color:#444'>This is the isolated POC test. If you got this, the credentials "
        "in <code>.env</code> are correct and we can wire the digest into the scheduler next.</p></div>")


def _env(key: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        sys.exit(f"missing required env var: {key} (add it to .env)")
    return val or ""


def _send_resend(api_key: str, to_addr: str, from_addr: str) -> None:
    import httpx  # app dependency; bundles proper CA certs (stdlib ssl has none on this Python)
    payload = {"from": from_addr, "to": [to_addr], "subject": SUBJECT, "html": HTML, "text": TEXT}
    print(f"sending via Resend API → {to_addr} (from {from_addr}) … (key not shown)")
    try:
        r = httpx.post("https://api.resend.com/emails", json=payload,
                       headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
    except Exception as e:  # noqa: BLE001 - surface any failure clearly, no secret leak
        sys.exit(f"❌ Resend send failed: {type(e).__name__}: {e}")
    if r.status_code >= 400:
        sys.exit(f"❌ Resend rejected ({r.status_code}): {r.text[:400]}")
    print(f"✅ Resend accepted the email (id={r.json().get('id', '?')}) → {to_addr}")


def _send_smtp(to_addr: str, from_addr: str) -> None:
    host = _env("RESUMAKER_SMTP_HOST", required=True)
    port = int(_env("RESUMAKER_SMTP_PORT", "587"))
    user = _env("RESUMAKER_SMTP_USER", required=True)
    password = _env("RESUMAKER_SMTP_PASS", required=True)   # read, never printed
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = SUBJECT, from_addr or user, to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=(from_addr or user).split("@")[-1] or "resumaker.local")
    msg.attach(MIMEText(TEXT, "plain"))
    msg.attach(MIMEText(HTML, "html"))
    print(f"sending via SMTP {host}:{port} as {user} … (password not shown)")
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(user, password)
                s.sendmail(from_addr or user, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(user, password)
                s.sendmail(from_addr or user, [to_addr], msg.as_string())
    except Exception as e:  # noqa: BLE001 - surface any failure clearly, no secret leak
        sys.exit(f"❌ SMTP send failed: {type(e).__name__}: {e}")
    print(f"✅ sent test email to {to_addr}")


def main() -> int:
    to_addr = _env("RESUMAKER_NOTIFY_TO", required=True)
    resend_key = _env("RESUMAKER_RESEND_API_KEY")
    if resend_key:
        _send_resend(resend_key, to_addr, _env("RESUMAKER_NOTIFY_FROM", "onboarding@resend.dev"))
    else:
        _send_smtp(to_addr, _env("RESUMAKER_NOTIFY_FROM"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
