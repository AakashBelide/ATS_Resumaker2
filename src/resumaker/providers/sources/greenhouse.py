"""Greenhouse board-listing adapter. Lists every open posting for a board token via the
public boards API (`boards-api.greenhouse.io/v1/boards/{token}/jobs`). The full JD is then
fetched on demand by `scrape/` using the per-job URL.

Bandwidth: Greenhouse supports conditional GET (ETag -> 304 Not Modified) and gzip, so on
an unchanged board we send `If-None-Match` and get a cheap 304 - the recommended way to
"avoid re-fetching old postings". A 304 returns [] (nothing new to ingest), which is
behaviorally identical to an unchanged board for dedupe.

Important: the conditional GET is only safe once we have actually persisted jobs for the
board. An ETag can get cached during onboarding/board-probe *before* the first real ingest;
if we then honored it, every subsequent ingest would get a 304 -> [] and the board would sit
at 0 jobs forever. So we only send `If-None-Match` when the board already has stored jobs -
the optimization kicks in for the steady state and stale pre-ingest ETags become harmless
(they're simply not sent until a full 200 fetch has populated the board).
"""
from __future__ import annotations

from resumaker.persistence import cache
from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_ETAG_NS = "gh_etag"


def _persisted_job_count(token: str) -> int:
    """How many greenhouse jobs are already stored for the company that owns this board token?
    Resolved via company_boards (URL-independent, so it stays correct regardless of whether we
    store the canonical or the company `absolute_url`). Failures count as 0 (fetch fully)."""
    try:
        from resumaker.persistence import db
        with db.connect() as conn:
            row = conn.execute(
                "SELECT count(*) FROM jobs WHERE source='greenhouse' AND company IN ("
                " SELECT c.name FROM companies c JOIN company_boards b ON b.company_id=c.id"
                " WHERE b.source='greenhouse' AND b.token=?)",
                (token,),
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001 - never let an index hiccup block a fetch
        return 0


class GreenhouseSource:
    source = "greenhouse"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
        etag_key = cache.make_key(token)
        prior = cache.get(_ETAG_NS, etag_key)
        # Only trust the conditional GET once the board is populated; otherwise a pre-ingest
        # ETag would keep the board pinned at 0 jobs (a 304 suppresses the full fetch).
        if prior and _persisted_job_count(token) > 0:
            headers["If-None-Match"] = prior
        r = polite_get(api, headers)
        if r.status_code == 304:            # unchanged since last poll - nothing new
            return []
        r.raise_for_status()
        if r.headers.get("ETag"):
            cache.put(_ETAG_NS, etag_key, r.headers["ETag"])
        out: list[PostingStub] = []
        for j in r.json().get("jobs", []) or []:
            jid = str(j.get("id", ""))
            canonical = f"https://boards.greenhouse.io/{token}/jobs/{jid}"
            # Prefer the company's `absolute_url` (greenhouse's own public link for the job):
            # for companies that redirect the greenhouse board to their site (e.g. Stripe), the
            # canonical URL 302s to a generic careers *landing*, whereas absolute_url opens the
            # actual role. For greenhouse-hosted boards absolute_url == canonical, so no change.
            abs_url = (j.get("absolute_url") or "").strip()
            out.append(PostingStub(
                source=self.source,
                external_id=jid,
                url=abs_url or canonical,
                title=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""),
                updated_at=j.get("updated_at", ""),
                extra={"absolute_url": abs_url, "canonical_url": canonical},
            ))
        return out
