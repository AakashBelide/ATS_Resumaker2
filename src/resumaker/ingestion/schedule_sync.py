"""Mailer send-frequency -> Cloud Scheduler (approach B).

The email digest has its own Cloud Scheduler job (`resumaker-mailer`, decoupled from ingestion),
so the Mailer page's "frequency" control maps directly to that job's cron: changing it rewrites
the schedule live, and "off" pauses the job (no emails) without touching discovery.

Cloud-only: without a GCP project configured (local dev / tests) this is a no-op. Lazy-imports
google-cloud-scheduler (the `cloud` extra) so the dependency only matters in the deploy.
"""
from __future__ import annotations

from resumaker.config import get_settings
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.ingestion.schedule_sync")

# Allowed send cadences -> their cron (Cloud Scheduler). "off" pauses the job (empty cron).
FREQUENCIES: dict[str, str] = {
    "off": "",
    "hourly": "0 * * * *",
    "every_4h": "0 */4 * * *",
    "every_12h": "0 */12 * * *",
    "daily": "0 8 * * *",
}


def sync_mailer_frequency(frequency: str) -> str:
    """Push the chosen send cadence to Cloud Scheduler; returns a short status string (for logs).
    No-op ('skipped') off-cloud. Never raises - a scheduler hiccup must not fail saving prefs
    (the prefs doc stays the source of truth, and the next save retries the sync)."""
    if frequency not in FREQUENCIES:
        frequency = "hourly"
    s = get_settings()
    if not (s.gcp_project and s.gcp_region and s.mailer_scheduler_job):
        return "skipped (no gcp)"
    try:
        from google.cloud import scheduler_v1  # lazy: only when the cloud backend is deployed
        client = scheduler_v1.CloudSchedulerServiceClient()
        name = client.job_path(s.gcp_project, s.gcp_region, s.mailer_scheduler_job)
        if frequency == "off":
            client.pause_job(name=name)
            _log.info("mailer frequency synced", extra={"frequency": frequency, "state": "paused"})
            return "paused"
        job = client.get_job(name=name)
        patch = scheduler_v1.Job(name=name, schedule=FREQUENCIES[frequency])
        client.update_job(job=patch, update_mask={"paths": ["schedule"]})
        if job.state == scheduler_v1.Job.State.PAUSED:   # turn a paused job back on
            client.resume_job(name=name)
        _log.info("mailer frequency synced",
                  extra={"frequency": frequency, "schedule": FREQUENCIES[frequency]})
        return f"schedule={FREQUENCIES[frequency]}"
    except Exception as e:  # noqa: BLE001 - never fail the save on a scheduler error
        _log.warning("mailer frequency sync failed", extra={"error": str(e)[:200]})
        return f"error: {e}"
