"""DOCX -> PDF via headless LibreOffice (deterministic, server-friendly) + helpers.

blueprint §4: LibreOffice `soffice --headless --convert-to pdf` is the deterministic
server/Docker path (matches a future Linux deploy). We also count pages (pypdf) for
the seniority-based length check.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader

_SOFFICE = shutil.which("soffice") or "/opt/homebrew/bin/soffice"


def docx_to_pdf(docx_path: str, out_dir: str | None = None) -> str:
    docx = Path(docx_path)
    out_dir = out_dir or str(docx.parent)
    proc = subprocess.run(
        [_SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", out_dir, str(docx)],
        capture_output=True, text=True, timeout=120)
    pdf = Path(out_dir) / (docx.stem + ".pdf")
    if proc.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"soffice conversion failed: {proc.stderr.strip()[:300]}")
    return str(pdf)


def page_count(pdf_path: str) -> int:
    return len(PdfReader(pdf_path).pages)


def extract_text(pdf_path: str) -> str:
    """Linear text extraction (round-trip ATS-parse check feeds Task 1.10)."""
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(pdf_path).pages)
