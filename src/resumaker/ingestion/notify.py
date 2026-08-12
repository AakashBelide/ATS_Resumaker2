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

# ---- brand theme (mirrors web/app/globals.css "Orbital Data" tokens) --------------------
# Emails inline every style (Gmail strips <style>/SVG), but we still ship the web fonts via an
# @import so clients that honor it (Apple Mail, Outlook-mac) render the real wordmark; the rest
# fall back through the same system stacks the site declares.
_BG, _SURFACE = "#060A14", "#0E1728"
_TEXT, _MUTED, _SKY = "#E9F0FB", "#93A7C9", "#8FBBFF"
_ELECTRIC, _AZURE, _CYAN, _GOOD = "#3B74FF", "#5B93FF", "#34D2E8", "#34e89e"
_LINE, _LINE2 = "rgba(126,164,224,0.14)", "rgba(126,164,224,0.28)"
_ACCENT = f"linear-gradient(90deg,{_ELECTRIC},{_CYAN})"
_F_DISPLAY = "'Space Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif"
_F_SANS = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif"
_F_MONO = "'Space Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# seniority pill palette, matching the .lvl.* classes in globals.css (color, bg, border).
_LVL_COLORS = {
    "intern":  (_CYAN, "rgba(52,210,232,0.08)", "rgba(52,210,232,0.30)"),
    "junior":  (_GOOD, "rgba(52,232,158,0.07)", "rgba(52,232,158,0.28)"),
    "senior":  (_AZURE, "rgba(59,116,255,0.08)", _LINE2),
    "staff":   ("#F2C24B", "rgba(242,194,75,0.07)", "rgba(242,194,75,0.28)"),
    "manager": ("#ff7a8a", "rgba(255,122,138,0.06)", "rgba(255,122,138,0.26)"),
}
_LVL_DEFAULT = (_MUTED, "rgba(255,255,255,0.03)", _LINE2)


def notify_new(jobs: list[JobRecord]) -> None:
    """Scheduler hook: durable digest (JSONL) + optional webhook for THIS tick's new postings.
    The email digest is sent separately by `email_pending` (driven off the fast tick), so it can
    email the whole pending backlog - not just this tick's new jobs - and honor quiet hours."""
    if not jobs:
        return
    _write_digest_and_webhook(jobs)


def email_pending() -> int:
    """Email the full pending on-target backlog (best-effort). Separate from `notify_new` so a
    quiet-hours / low-frequency deferral catches up whenever the digest next runs, and so a tick
    that ingested nothing new still flushes a backlog left from an earlier deferral."""
    try:
        return email_new(db.list_jobs(limit=100_000))
    except Exception as e:  # noqa: BLE001 - notification is best-effort, never sinks a tick
        _log.warning("email digest failed", extra={"error": str(e)})
        return 0


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


def _mailer_predicate(mp: dict):
    """Build the 'is this posting worth emailing?' test from a Mailer-prefs dict: on-target
    (owner's target roles) AND title has/hasn't AND seniority level AND US state. Empty filters
    = no extra narrowing. Shared by `pending` (what to send) and `preview_counts` (the live
    'X of N' the Mailer page shows), so the page's preview can never drift from the real filter."""
    from resumaker.ingestion.service import (
        matches_preferences,
        title_level,
        title_matches,
        us_states_of,
    )
    inc, exc = mp.get("include") or [], mp.get("exclude") or []
    levels = {x.lower() for x in (mp.get("levels") or [])}
    states = mp.get("states") or []

    def keep(j: JobRecord) -> bool:
        if not (matches_preferences(j.title) and title_matches(j.title, inc, exc)):
            return False
        if levels and title_level(j.title).lower() not in levels:
            return False
        if states:
            js = us_states_of(j.location)
            if not any((not js) if s == "OTHER" else s in js for s in states):
                return False
        return True

    return keep


def pending(jobs: list[JobRecord]) -> list[JobRecord]:
    """The subset worth emailing: on-target, passing the owner's Mailer filters (title has/hasn't,
    seniority level, US state — all editable on the Mailer page), AND not already emailed. Empty
    filters = no extra narrowing."""
    from resumaker.persistence.profile import load_mailer_prefs
    keep = _mailer_predicate(load_mailer_prefs())
    return db.unnotified([j for j in jobs if keep(j)])


def preview_counts(mp: dict) -> dict[str, int]:
    """Live tuning aid for the Mailer page: given a (possibly unsaved) filter, how many stored
    on-target postings match, and how many a digest would actually send under the cap. Counts
    the whole `jobs` table (already tech+US-gated at ingest), independent of what's been emailed
    already, so the page can show 'this filter matches X of N on-target postings'."""
    from resumaker.ingestion.service import matches_preferences
    keep = _mailer_predicate(mp)
    jobs = db.list_jobs(limit=100_000)
    on_target = sum(1 for j in jobs if matches_preferences(j.title))
    matching = sum(1 for j in jobs if keep(j))
    cap = int(mp.get("max_postings") or 0)
    return {"on_target": on_target, "matching": matching,
            "cap": cap, "would_send": min(cap, matching) if cap else matching}


def _in_quiet_hours(mp: dict) -> bool:
    """True if 'now' (in the mailer timezone) falls in the quiet window; supports a window that
    wraps midnight (e.g. 22:00 -> 07:00). quiet_enabled=False or an empty start/end = never quiet."""
    if not mp.get("quiet_enabled", True):
        return False
    qs, qe = (mp.get("quiet_start") or "").strip(), (mp.get("quiet_end") or "").strip()
    if not (qs and qe):
        return False
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(mp.get("timezone") or "UTC")).strftime("%H:%M")
    except Exception:  # noqa: BLE001 - bad tz -> don't block sending
        return False
    return qs <= now < qe if qs <= qe else (now >= qs or now < qe)


def email_new(jobs: list[JobRecord], *, dry_run: bool = False) -> int:
    """Email a digest of new on-target postings not yet sent. Returns how many were included.
    No candidates, or no recipient/sender configured -> no-op. `dry_run` builds but doesn't
    send or mark. Honors the Mailer page's quiet hours (defer) + max-postings cap (send the
    top N, show 'X of total', and mark the rest seen so they surface in Discovery not email)."""
    from resumaker.persistence.profile import load_mailer_prefs
    s = get_settings()
    mp = load_mailer_prefs()
    candidates = pending(jobs)
    total = len(candidates)
    if total == 0:
        return 0
    if not dry_run and _in_quiet_hours(mp):   # defer WITHOUT marking, so they send after the window
        _log.info("email digest deferred (quiet hours)", extra={"pending": total})
        return 0
    cap = int(mp.get("max_postings") or 0)
    to_send = candidates[:cap] if cap > 0 else candidates
    if dry_run:                               # preview count works without any email config
        return total
    if not s.notify_to or not (s.resend_api_key or s.smtp_host):
        _log.info("email digest skipped: set RESUMAKER_NOTIFY_TO + a sender (Resend/SMTP) in .env",
                  extra={"pending": total})
        return 0
    subject, html_body, text_body = build_digest(to_send, total=total, tz=mp.get("timezone"))
    _send(s, subject, html_body, text_body)
    db.mark_notified(candidates)              # mark ALL seen; the capped-out ones live in Discovery
    _log.info("emailed digest", extra={"count": len(to_send), "of": total, "to": s.notify_to})
    return len(to_send)


_DEFAULT_TZ = "America/New_York"


def _fmt_local_dt(dt: datetime, tz: str) -> str:
    """A posting datetime as a clean local 'Aug 12, 2026, 3:30 PM' in the mailer timezone.
    first_seen is stored UTC; render it where the owner reads email (matches the Discovery card)."""
    from zoneinfo import ZoneInfo
    try:
        aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        dt = aware.astimezone(ZoneInfo(tz))
    except Exception:  # noqa: BLE001 - bad tz -> render as-is
        pass
    date = dt.strftime("%b %d, %Y").replace(" 0", " ")
    time = dt.strftime("%I:%M %p").lstrip("0")   # 03:30 PM -> 3:30 PM
    return f"{date}, {time}"


def _posting_date(j: JobRecord, tz: str = _DEFAULT_TZ) -> str:
    """Best per-posting date for the digest: the source's posting date when parseable, else
    when we first fetched it (shown with the exact local time). Workday-style relative text
    ('Posted 3 Days Ago') is shown as-is."""
    raw = (j.posted_at or "").strip()
    if raw:
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return "posted " + d.strftime("%b %d, %Y").replace(" 0", " ")
        except ValueError:
            return raw                       # e.g. Workday "Posted 3 Days Ago"
    if j.first_seen:
        return "added " + _fmt_local_dt(j.first_seen, tz)
    return ""


def _pill(text: str, color: str, bg: str, border: str) -> str:
    """A mono, uppercase micro-badge in the site's .lvl / .tag idiom."""
    return (f"<span style=\"font-family:{_F_MONO};font-size:10px;letter-spacing:.6px;"
            f"text-transform:uppercase;color:{color};background:{bg};"
            f"border:1px solid {border};border-radius:6px;padding:3px 9px;"
            f"display:inline-block;line-height:1.4\">{html_lib.escape(text)}</span>")


def _brand_header(n: int, total: int | None = None) -> str:
    """Hex-badge + wordmark lockup, accent divider, and the headline — the site's rail brand
    rendered email-safe (a gradient tile with the ⬢ glyph stands in for the stroked SVG hex,
    which Gmail would strip). When capped, the headline reads 'n of total'."""
    total = n if total is None else total
    capped = total > n
    plural = "" if n == 1 else "s"
    headline = f"{n} of {total} new on-target postings" if capped else f"{n} new on-target posting{plural}"
    subline = (f"showing the top {n} of {total} — see the rest in Discovery" if capped
               else "from your ATS Resumaker watchlist")
    return (
        "<tr><td style=\"padding:0 0 18px\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\"><tr>"
        f"<td style=\"width:40px;height:40px;border-radius:10px;text-align:center;"
        f"vertical-align:middle;background:linear-gradient(135deg,{_ELECTRIC},{_AZURE});"
        f"font-size:20px;line-height:40px;color:#061024;"
        f"box-shadow:0 8px 22px rgba(59,116,255,0.28)\">&#11042;</td>"
        "<td style=\"padding-left:12px;vertical-align:middle\">"
        f"<div style=\"font-family:{_F_DISPLAY};font-size:19px;font-weight:700;color:{_TEXT};"
        "letter-spacing:0.2px;line-height:1.1\">ATS Resumaker</div>"
        f"<div style=\"font-family:{_F_MONO};font-size:8.5px;letter-spacing:2px;"
        f"text-transform:uppercase;color:{_MUTED};margin-top:3px\">watchlist &middot; discovery</div>"
        "</td></tr></table></td></tr>"
        f"<tr><td style=\"padding:0 0 24px\"><div style=\"height:3px;border-radius:3px;"
        f"background:{_ACCENT}\"></div></td></tr>"
        "<tr><td style=\"padding:0 0 22px\">"
        f"<div style=\"font-family:{_F_MONO};font-size:11px;letter-spacing:2px;"
        f"text-transform:uppercase;color:{_SKY};margin:0 0 8px\">&mdash; new on-target</div>"
        f"<div style=\"font-family:{_F_DISPLAY};font-size:24px;font-weight:700;color:{_TEXT};"
        f"letter-spacing:-0.4px;line-height:1.2\">{html_lib.escape(headline)}</div>"
        f"<div style=\"color:{_MUTED};font-size:13px;margin-top:6px\">"
        f"{html_lib.escape(subline)}</div></td></tr>")


def _card_html(j: JobRecord, tz: str = _DEFAULT_TZ) -> str:
    """A single posting as a themed .jobcard: accent top-strip, display-font title link,
    sky company, and a mono meta row (seniority pill + source + comp + date)."""
    from resumaker.ingestion.service import title_level
    lvl = title_level(j.title)
    color, bg, border = _LVL_COLORS.get(lvl, _LVL_DEFAULT)

    pills = [_pill(lvl, color, bg, border)]
    if j.source:
        pills.append(_pill(j.source, _MUTED, "rgba(255,255,255,0.03)", _LINE2))
    date = _posting_date(j, tz)
    if date:
        pills.append(f"<span style=\"font-family:{_F_MONO};font-size:11px;color:{_MUTED}\">"
                     f"{html_lib.escape(date)}</span>")
    if j.comp:
        pills.append(f"<span style=\"font-size:12.5px;font-weight:600;color:{_GOOD}\">"
                     f"{html_lib.escape(j.comp)}</span>")
    meta_pills = "".join(f"<td style=\"padding:0 8px 0 0\">{p}</td>" for p in pills)

    co_line = html_lib.escape(j.company)
    if j.location:
        co_line += f" &middot; {html_lib.escape(j.location)}"

    return (
        f"<tr><td style=\"padding:0 0 12px\"><div style=\"border-radius:14px;overflow:hidden;"
        f"border:1px solid {_LINE};background:{_SURFACE}\">"
        f"<div style=\"height:3px;background:{_ACCENT}\"></div>"
        "<div style=\"padding:15px 18px\">"
        f"<a href=\"{html_lib.escape(j.url)}\" style=\"font-family:{_F_DISPLAY};color:{_SKY};"
        "font-weight:600;font-size:16px;text-decoration:none;line-height:1.3;"
        f"letter-spacing:-0.2px\">{html_lib.escape(j.title)}</a>"
        f"<div style=\"color:{_SKY};font-size:13.5px;margin-top:5px\">{co_line}</div>"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" "
        f"style=\"margin-top:12px\"><tr>{meta_pills}</tr></table>"
        "</div></div></td></tr>")


def build_digest(jobs: list[JobRecord], *, total: int | None = None,
                 tz: str | None = None) -> tuple[str, str, str]:
    """Return (subject, html, text) for a grouped, readable digest. `total` (>= len(jobs)) is the
    full pending count when the max-postings cap trimmed the list — shown as 'n of total'. `tz` is
    the mailer timezone the per-posting 'added' time is rendered in (defaults to America/New_York)."""
    from resumaker.ingestion.service import title_level
    tz = tz or _DEFAULT_TZ
    n = len(jobs)
    total = n if total is None else total
    subject = (f"ATS Resumaker — {n} of {total} new on-target postings" if total > n
               else f"ATS Resumaker — {n} new on-target posting{'' if n == 1 else 's'}")
    ordered = sorted(jobs, key=lambda j: (j.company.lower(), j.title.lower()))

    cards_html, rows_text = [], []
    for j in ordered:
        meta = " · ".join(x for x in [j.location, (j.comp or ""), title_level(j.title),
                                      j.source, _posting_date(j, tz)] if x)
        cards_html.append(_card_html(j, tz))
        rows_text.append(f"- {j.title} — {j.company} ({meta})\n  {j.url}")

    html_body = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700"
        "&family=Space+Mono:wght@400;700&family=Inter:wght@400;500;600&display=swap');"
        "body{margin:0;padding:0;background:" + _BG + ";}</style></head>"
        f"<body style=\"margin:0;padding:0;background:{_BG};font-family:{_F_SANS};color:{_TEXT}\">"
        f"<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        f"style=\"background:{_BG}\"><tr><td align=\"center\" style=\"padding:32px 16px\">"
        "<table role=\"presentation\" width=\"600\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"max-width:600px;width:100%\">"
        + _brand_header(n, total)
        + "".join(cards_html)
        + f"<tr><td style=\"padding:20px 2px 0\"><div style=\"font-family:{_F_MONO};font-size:10px;"
        f"letter-spacing:1px;color:{_MUTED};border-top:1px solid {_LINE};padding-top:14px\">"
        "ATS RESUMAKER &middot; v0.1 &middot; SELF-HOSTED</div></td></tr>"
        "</table></td></tr></table></body></html>")
    text_head = (f"{n} of {total} new on-target postings (see the rest in Discovery)" if total > n
                 else f"{n} new on-target posting{'' if n == 1 else 's'} from your ATS Resumaker watchlist")
    text_body = f"{text_head}:\n\n" + "\n\n".join(rows_text)
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
