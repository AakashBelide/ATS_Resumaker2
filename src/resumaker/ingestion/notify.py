"""Notifications for newly-ingested postings (RI.4).

Always writes a durable digest line (JSONL under the output dir) and structured-logs a
summary; if `notify_webhook` is set, POSTs the digest there. NEW: if an email recipient +
sender are configured (all via .env - nothing hardcoded), emails a digest of new *on-target*
postings, deduped so a posting is never emailed twice. Human decides what to act on - nothing
auto-applies (blueprint §21)."""
from __future__ import annotations

import html as html_lib
import json
from datetime import UTC, datetime

from resumaker.config import get_settings
from resumaker.domain import JobRecord
from resumaker.observability.logging import get_logger
from resumaker.persistence import db

_log = get_logger("resumaker.ingestion.notify")


def notify_new(jobs: list[JobRecord]) -> None:
    """Scheduler hook: durable digest + optional webhook, then the email digest (best-effort)."""
    if not jobs:
        return
    _write_digest_and_webhook(jobs)
    try:
        email_new(jobs)
    except Exception as e:  # noqa: BLE001 - notification is best-effort, never sinks a tick
        _log.warning("email digest failed", extra={"error": str(e)})


def _write_digest_and_webhook(jobs: list[JobRecord]) -> None:
    digest = {
        "ts": datetime.now(UTC).isoformat(),
        "count": len(jobs),
        "jobs": [{"company": j.company, "title": j.title, "url": j.url,
                  "location": j.location} for j in jobs],
    }
    s = get_settings()
    path = s.output_root / "_watchlist_digest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(digest) + "\n")
    _log.info("new postings", extra={"count": len(jobs)})

    if s.notify_webhook:
        try:
            import httpx
            httpx.post(s.notify_webhook, json=digest, timeout=10)
        except Exception as e:  # noqa: BLE001 - notification best-effort
            _log.warning("webhook notify failed", extra={"error": str(e)})


def pending(jobs: list[JobRecord]) -> list[JobRecord]:
    """The subset worth emailing: on-target (target-role match) AND not already emailed."""
    from resumaker.ingestion.service import matches_preferences
    on_target = [j for j in jobs if matches_preferences(j.title)]
    return db.unnotified(on_target)


def email_new(jobs: list[JobRecord], *, dry_run: bool = False) -> int:
    """Email a digest of new on-target postings not yet sent. Returns how many were included.
    No candidates, or no recipient/sender configured -> no-op. `dry_run` builds but doesn't
    send or mark."""
    s = get_settings()
    candidates = pending(jobs)
    if not candidates:
        return 0
    if dry_run:                              # preview count works without any email config
        return len(candidates)
    if not s.notify_to or not (s.resend_api_key or s.smtp_host):
        _log.info("email digest skipped: set RESUMAKER_NOTIFY_TO + a sender (Resend/SMTP) in .env",
                  extra={"pending": len(candidates)})
        return 0
    subject, html_body, text_body = build_digest(candidates)
    _send(s, subject, html_body, text_body)
    db.mark_notified(candidates)
    _log.info("emailed digest", extra={"count": len(candidates), "to": s.notify_to})
    return len(candidates)


def _posting_date(j: JobRecord) -> str:
    """Best per-posting date for the digest: the source's posting date when parseable, else
    when we first fetched it. Workday-style relative text ('Posted 3 Days Ago') is shown as-is."""
    raw = (j.posted_at or "").strip()
    if raw:
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return "posted " + d.strftime("%b %d, %Y").replace(" 0", " ")
        except ValueError:
            return raw                       # e.g. Workday "Posted 3 Days Ago"
    if j.first_seen:
        return "added " + j.first_seen.strftime("%b %d, %Y").replace(" 0", " ")
    return ""


def build_digest(jobs: list[JobRecord]) -> tuple[str, str, str]:
    """Return (subject, html, text) for a grouped, readable digest of the given postings."""
    from resumaker.ingestion.service import title_level
    n = len(jobs)
    subject = f"ATS Resumaker — {n} new on-target posting{'' if n == 1 else 's'}"
    ordered = sorted(jobs, key=lambda j: (j.company.lower(), j.title.lower()))

    cards_html, rows_text = [], []
    for j in ordered:
        meta = " · ".join(x for x in [j.location, (j.comp or ""), title_level(j.title),
                                      j.source, _posting_date(j)] if x)
        cards_html.append(
            "<div style='background:#0E1728;border:1px solid #1e2a44;border-radius:12px;"
            "padding:14px 16px;margin:0 0 12px'>"
            f"<a href='{html_lib.escape(j.url)}' style='color:#8FBBFF;text-decoration:none;"
            f"font-weight:600;font-size:15px'>{html_lib.escape(j.title)}</a>"
            f"<div style='color:#93A7C9;font-size:13px;margin-top:5px'>"
            f"{html_lib.escape(j.company)} — {html_lib.escape(meta)}</div></div>")
        rows_text.append(f"- {j.title} — {j.company} ({meta})\n  {j.url}")

    html_body = (
        "<div style='background:#060A14;color:#E9F0FB;"
        "font-family:system-ui,-apple-system,Arial,sans-serif;padding:24px'>"
        f"<h2 style='margin:0 0 4px;font-size:20px'>{n} new on-target posting{'' if n == 1 else 's'}</h2>"
        "<p style='color:#93A7C9;margin:0 0 18px;font-size:13px'>from your ATS Resumaker watchlist</p>"
        f"{''.join(cards_html)}</div>")
    text_body = (f"{n} new on-target posting{'' if n == 1 else 's'} from your ATS Resumaker watchlist:\n\n"
                 + "\n\n".join(rows_text))
    return subject, html_body, text_body


def _send(s, subject: str, html_body: str, text_body: str) -> None:
    if s.resend_api_key:
        import httpx
        r = httpx.post(
            "https://api.resend.com/emails",
            json={"from": s.notify_from, "to": [s.notify_to], "subject": subject,
                  "html": html_body, "text": text_body},
            headers={"Authorization": f"Bearer {s.resend_api_key}"}, timeout=20)
        r.raise_for_status()
        return
    _send_smtp(s, subject, html_body, text_body)


def _send_smtp(s, subject: str, html_body: str, text_body: str) -> None:
    import smtplib
    import ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender = s.notify_from or s.smtp_user
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = s.notify_to
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    ctx = ssl.create_default_context()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx, timeout=20) as srv:
            srv.login(s.smtp_user, s.smtp_pass)
            srv.sendmail(sender, [s.notify_to], msg.as_string())
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as srv:
            srv.ehlo()
            srv.starttls(context=ctx)
            srv.ehlo()
            srv.login(s.smtp_user, s.smtp_pass)
            srv.sendmail(sender, [s.notify_to], msg.as_string())
