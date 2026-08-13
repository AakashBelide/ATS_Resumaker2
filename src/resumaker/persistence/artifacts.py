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

from contextlib import suppress
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
    def delete_run(self, run_id: str) -> None: ...
    def find(self, run_id: str, suffix: str) -> str | None: ...
    def purge(self, run_id: str, suffixes: tuple[str, ...]) -> None: ...


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

    def delete_run(self, run_id: str) -> None:
        import shutil
        d = get_settings().output_root / run_id
        shutil.rmtree(d, ignore_errors=True)

    def find(self, run_id: str, suffix: str) -> str | None:
        d = get_settings().output_root / run_id
        m = next((f for f in d.glob(f"*{suffix}")), None)
        return m.name if m else None

    def purge(self, run_id: str, suffixes: tuple[str, ...]) -> None:
        d = get_settings().output_root / run_id
        if not d.is_dir():
            return
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in suffixes:
                with suppress(Exception):
                    f.unlink()


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

    def delete_run(self, run_id: str) -> None:
        # Remove every blob under gs://bucket/<run_id>/ (the whole run folder), then the local
        # temp copy. Used to clear stale artifacts before a re-match and to purge a deleted job.
        for blob in self._bucket().list_blobs(prefix=f"{run_id}/"):
            with suppress(Exception):
                blob.delete()
        self._local.delete_run(run_id)

    def find(self, run_id: str, suffix: str) -> str | None:
        # Resolve a role-slug artifact (e.g. the resume PDF/DOCX) by suffix from the BUCKET, not
        # the local temp dir - on a scale-to-zero instance that local dir is empty (the files live
        # in GCS after publish), which is why serving resume.pdf/docx used to 404.
        for blob in self._bucket().list_blobs(prefix=f"{run_id}/"):
            name = blob.name.rsplit("/", 1)[-1]
            if name.endswith(suffix):
                return name
        return None

    def purge(self, run_id: str, suffixes: tuple[str, ...]) -> None:
        # Delete every blob under the run whose filename ends in one of `suffixes` (e.g. drop a
        # stale generated resume .pdf/.docx before writing an uploaded one), then the local copies.
        for blob in self._bucket().list_blobs(prefix=f"{run_id}/"):
            name = blob.name.rsplit("/", 1)[-1].lower()
            if any(name.endswith(s) for s in suffixes):
                with suppress(Exception):
                    blob.delete()
        self._local.purge(run_id, suffixes)

    def url(self, run_id: str, name: str) -> str | None:
        from datetime import timedelta
        blob = self._bucket().blob(f"{run_id}/{Path(name).name}")
        if not blob.exists():
            return None
        # On Cloud Run the runtime credentials are a bare OAuth token with no private key, so
        # generate_signed_url can't sign locally. Sign via the IAM signBlob API instead by
        # passing the SA email + a fresh access token (needs roles/iam.serviceAccountTokenCreator
        # on the SA itself). Off-cloud creds that DO carry a private key sign directly (kwargs stay
        # empty). See google-cloud-storage signed-URL docs for the compute-credentials path.
        sign_kwargs: dict = {}
        try:
            import google.auth
            from google.auth.transport.requests import Request
            creds, _ = google.auth.default()
            creds.refresh(Request())
            email = getattr(creds, "service_account_email", None)
            token = getattr(creds, "token", None)
            if email and email != "default" and token:
                sign_kwargs = {"service_account_email": email, "access_token": token}
        except Exception:  # noqa: BLE001 - fall back to direct signing (local key-based creds)
            pass
        return blob.generate_signed_url(version="v4", method="GET",
                                        expiration=timedelta(seconds=self._ttl), **sign_kwargs)


def get_artifact_store() -> ArtifactStore:
    """Config-selected store. Defaults to local disk; `RESUMAKER_ARTIFACT_BACKEND=gcs` (with
    `gcs_bucket` set) switches to GCS."""
    s = get_settings()
    if s.artifact_backend == "gcs":
        if not s.gcs_bucket:
            raise RuntimeError("artifact_backend=gcs needs gcs_bucket")
        return GCSArtifactStore(s.gcs_bucket)
    return LocalArtifactStore()
