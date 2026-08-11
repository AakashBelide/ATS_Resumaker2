"""Minimal, faithful shim of the real `base` module so a DRAFT adapter can be run + tested
INSIDE the sandbox (untrusted generated code never runs on the host). The field/interface shape
matches the real PostingStub/SourceAdapter, so passing here ⇒ it plugs into the real registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PostingStub:
    source: str
    external_id: str
    url: str
    title: str
    location: str = ""
    updated_at: str = ""
    comp: str = ""
    extra: dict = field(default_factory=dict)


class SourceAdapter(Protocol):
    source: str

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        ...
