"""LLM spend summary + Gemini budget headroom (the AIOps cost view)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.security import require_token
from resumaker.observability import cost

router = APIRouter(prefix="/v1/costs", tags=["costs"], dependencies=[Depends(require_token)])


@router.get("")
def costs() -> dict:
    return cost.summary()
