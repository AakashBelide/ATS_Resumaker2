"""POC: send ONE test notification email via SMTP (STARTTLS on 587, or SSL on 465).

Standalone, deliberately dependency-free — proves the mail path works before we wire it into
the scheduler. Config comes from the environment (populate .env; it is gitignored and never
committed). The password is read from env and NEVER printed/logged.

Env (see .env.example):
  RESUMAKER_SMTP_HOST      e.g. smtp.gmail.com
  RESUMAKER_SMTP_PORT      587 (STARTTLS) or 465 (SSL); default 587
  RESUMAKER_SMTP_USER      the sending account, e.g. you@gmail.com
  RESUMAKER_SMTP_PASS      Gmail App Password (16 chars, no spaces) — NOT your real password
  RESUMAKER_NOTIFY_TO      recipient (can be the same address)
  RESUMAKER_NOTIFY_FROM    optional; defaults to SMTP_USER

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


def _env(key: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        sys.exit(f"missing required env var: {key} (add it to .env)")
    return val or ""


def main() -> int:
    host = _env("RESUMAKER_SMTP_HOST", required=True)
    port = int(_env("RESUMAKER_SMTP_PORT", "587"))
    user = _env("RESUMAKER_SMTP_USER", required=True)
    password = _env("RESUMAKER_SMTP_PASS", required=True)   # read, never printed
    to_addr = _env("RESUMAKER_NOTIFY_TO", required=True)
    from_addr = _env("RESUMAKER_NOTIFY_FROM", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "resumaker — mailer POC ✅"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_addr.split("@")[-1] or "resumaker.local")
    msg.attach(MIMEText("resumaker mailer POC — SMTP is wired correctly.", "plain"))
    msg.attach(MIMEText(
        "<div style='font-family:system-ui,sans-serif'>"
        "<h2 style='margin:0 0 8px'>resumaker mailer works ✅</h2>"
        "<p style='color:#444'>This is the isolated POC test. If you got this, the SMTP "
        "credentials in <code>.env</code> are correct and we can wire the digest into the "
        "scheduler next.</p></div>", "html"))

    print(f"connecting to {host}:{port} as {user} … (password not shown)")
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(user, password)
                s.sendmail(from_addr, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(user, password)
                s.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception as e:  # noqa: BLE001 - POC: surface any failure clearly, no secret leak
        sys.exit(f"❌ send failed: {type(e).__name__}: {e}")
    print(f"✅ sent test email to {to_addr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
