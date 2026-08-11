"""Job-queue seam (D.4): how a pipeline run gets executed - dual-mode.

`POST /v1/runs` mints a run id and hands it to the queue; where the work actually runs is the
config-selected part:

  - InProcessQueue (local default): submit to the in-process ThreadPoolExecutor (the existing
    RunManager). Zero infra - a single box runs the pipeline off the request thread.
  - CloudTasksQueue (cloud): enqueue a Cloud Task that POSTs to the WORKER service's
    /v1/worker/run-pipeline. Cloud Run is request-based, so long jobs can't live in-process
    there; Cloud Tasks is the durable work queue (retries on non-2xx, decoupled from the api).

Same call site either way (`get_job_queue().submit_pipeline(run_id, url, options)`), so the
API code doesn't fork. Mirrors the AgentRunner seam used for onboarding.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from resumaker.config import get_settings
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.api.queue")


class JobQueue(Protocol):
    def submit_pipeline(self, run_id: str, url: str, options: dict[str, Any]) -> None: ...


class InProcessQueue:
    """Local default: run on the shared RunManager's ThreadPoolExecutor."""

    def __init__(self, manager: Any):
        self._manager = manager

    def submit_pipeline(self, run_id: str, url: str, options: dict[str, Any]) -> None:
        self._manager.submit(run_id, url, **options)


class CloudTasksQueue:
    """Cloud: enqueue an HTTP Cloud Task to the worker's /v1/worker/run-pipeline.

    The task body is the run request; Cloud Run holds the request while the worker runs the
    pipeline synchronously and Cloud Tasks retries on non-2xx. Auth: the api token is sent as a
    header (the worker enforces it), so Scheduler/Tasks and the api share the single-user secret.
    """

    def __init__(self, *, project: str, region: str, queue: str, worker_url: str,
                 token: str | None):
        self._project = project
        self._region = region
        self._queue = queue
        self._worker_url = worker_url.rstrip("/")
        self._token = token

    def submit_pipeline(self, run_id: str, url: str, options: dict[str, Any]) -> None:
        from google.cloud import tasks_v2  # lazy: only when cloud_tasks is selected

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(self._project, self._region, self._queue)
        body = json.dumps({"run_id": run_id, "url": url, **options}).encode()
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["X-API-Key"] = self._token
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self._worker_url}/v1/worker/run-pipeline",
                "headers": headers,
                "body": body,
            },
            # dedupe: one task per run id (Cloud Tasks drops duplicates by name for ~1h)
            "name": client.task_path(self._project, self._region, self._queue, run_id),
        }
        client.create_task(parent=parent, task=task)
        _log.info("enqueued pipeline task", extra={"run_id": run_id, "queue": self._queue})


def get_job_queue() -> JobQueue:
    """Config-selected queue. Defaults to in-process; `RESUMAKER_JOB_QUEUE=cloud_tasks` (with
    gcp_project/region + worker_url set) switches to Cloud Tasks."""
    s = get_settings()
    if s.job_queue == "cloud_tasks":
        missing = [k for k, v in (("gcp_project", s.gcp_project), ("gcp_region", s.gcp_region),
                                  ("worker_url", s.worker_url)) if not v]
        if missing:
            raise RuntimeError(f"job_queue=cloud_tasks needs {', '.join(missing)}")
        assert s.gcp_project and s.gcp_region and s.worker_url  # for type-narrowing
        return CloudTasksQueue(project=s.gcp_project, region=s.gcp_region, queue=s.tasks_queue,
                               worker_url=s.worker_url, token=s.api_token)
    from apps.api.jobs.worker import manager
    return InProcessQueue(manager)
