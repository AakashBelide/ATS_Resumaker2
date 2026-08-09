"""API auth. Single-user, so a single bearer token is enough - but an exposed VM must
never be open, so when `RESUMAKER_API_TOKEN` is set every request must present it
(Authorization: Bearer <token> or X-API-Key). If unset (local dev), access is open and
we log a one-time warning."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from resumaker.config import get_settings
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.api")
_warned = False


def require_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    global _warned
    token = get_settings().api_token
    if not token:
        if not _warned:
            _log.warning("API auth disabled (RESUMAKER_API_TOKEN unset) - do not expose")
            _warned = True
        return
    presented = x_api_key or (authorization.removeprefix("Bearer ").strip()
                              if authorization else None)
    if presented != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="missing or invalid API token")
