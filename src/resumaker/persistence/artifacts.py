"""Artifact-store seam (D.5): where a run's files live - dual-mode.

A run writes its artifacts (resume .docx/.pdf, report.json, JD.txt, status.json...) to a
directory; where that directory is durable is the config-selected part:

  - LocalArtifactStore (default): the run dir under `output_dir`. Durable on a real disk /
    mounted volume; the API serves files inline. Zero infra.
  - GCSArtifactStore (cloud): Cloud Run has no persistent disk, so the run still WRITES to a
    local temp dir (LibreOffice needs a real FS), then `publish()` uploads it to a bucket; the
    API hands back a signed URL instead of streaming. Survives the instance going away.

`local_run_dir()` is always a real local path (the pipeline + LibreOffice write there). `publish()`
is a no-op locally and an upload in the cloud. `url()` returns None locally (serve inline) or a
signed URL in the cloud. Mirrors the JobQueue / AgentRunner seams.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from resumaker.config import get_settings
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.artifacts")


class ArtifactStore(Protocol):
    def local_run_dir(self, run_id: str) -> Path: ...
    def publish(self, run_id: str) -> None: ...
    def open(self, run_id: str, name: str) -> bytes | None: ...
    def url(self, run_id: str, name: str) -> str | None: ...


class LocalArtifactStore:
    """Default: artifacts stay on local disk under `output_dir`; served inline by the API."""

    def local_run_dir(self, run_id: str) -> Path:
        d = get_settings().output_root / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def publish(self, run_id: str) -> None:
        return None  # already durable on disk

    def open(self, run_id: str, name: str) -> bytes | None:
        p = self.local_run_dir(run_id) / Path(name).name  # basename only - no traversal
        return p.read_bytes() if p.is_file() else None

    def url(self, run_id: str, name: str) -> str | None:
        return None  # no external URL - the API streams the file


class GCSArtifactStore:
    """Cloud: run writes to a local temp dir, `publish()` uploads it to gs://bucket/<run_id>/,
    and `url()` returns a short-lived signed URL. Lazy-imports google-cloud-storage so the
    dependency only matters when this backend is selected."""

    def __init__(self, bucket: str, *, signed_ttl_s: int = 900):
        self._bucket_name = bucket
        self._ttl = signed_ttl_s
        self._local = LocalArtifactStore()

    def _bucket(self):
        from google.cloud import storage  # lazy: only when gcs is selected
        return storage.Client().bucket(self._bucket_name)

    def local_run_dir(self, run_id: str) -> Path:
        return self._local.local_run_dir(run_id)  # still a real FS for the run

    def publish(self, run_id: str) -> None:
        bucket = self._bucket()
        run_dir = self._local.local_run_dir(run_id)
        for f in run_dir.rglob("*"):
            if f.is_file():
                bucket.blob(f"{run_id}/{f.relative_to(run_dir).as_posix()}").upload_from_filename(f)
        _log.info("published run to gcs", extra={"run_id": run_id, "bucket": self._bucket_name})

    def open(self, run_id: str, name: str) -> bytes | None:
        blob = self._bucket().blob(f"{run_id}/{Path(name).name}")
        return blob.download_as_bytes() if blob.exists() else None

    def url(self, run_id: str, name: str) -> str | None:
        from datetime import timedelta
        blob = self._bucket().blob(f"{run_id}/{Path(name).name}")
        if not blob.exists():
            return None
        return blob.generate_signed_url(expiration=timedelta(seconds=self._ttl))


def get_artifact_store() -> ArtifactStore:
    """Config-selected store. Defaults to local disk; `RESUMAKER_ARTIFACT_BACKEND=gcs` (with
    `gcs_bucket` set) switches to GCS."""
    s = get_settings()
    if s.artifact_backend == "gcs":
        if not s.gcs_bucket:
            raise RuntimeError("artifact_backend=gcs needs gcs_bucket")
        return GCSArtifactStore(s.gcs_bucket)
    return LocalArtifactStore()
