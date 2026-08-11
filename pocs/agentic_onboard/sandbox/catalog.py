"""Source catalog = the single source of truth for BOTH what the agent can resolve AND what the
sandbox may reach. The egress allow-list is GENERATED from this, never hand-maintained.

Why this resolves the "what if a company's host isn't on the list?" tension:
  * The system can only onboard a company to a source it has an ADAPTER for. That set is finite
    and known (here 6; in production it's the full `providers/sources` registry of ~25). So a
    *resolvable* board is always one of these sources, and its host is on the list by construction.
  * Adding support for a new ATS = adding an adapter = adding its host HERE, in one place. That's
    a deliberate, code-reviewed change — exactly where a security-relevant egress change belongs,
    NOT at agent runtime.
  * A company whose board we can't guess and whose ATS host isn't known goes to the `needs_input`
    path: the human supplies the careers URL, and THAT host is allow-listed just-in-time for that
    one run (per-run EXTRA_ALLOW). So nothing is ever silently blocked — it's either a known
    source (already allowed) or a human-approved one-off.

In integration, replace SOURCE_HOSTS with a projection of the real adapter registry (each adapter
declaring the host(s) it fetches), so the allow-list can never drift from what's actually onboardable.
"""
from __future__ import annotations

from pathlib import Path

# source -> egress host(s). Leading-dot = subdomain wildcard (workday tenants).
SOURCE_HOSTS: dict[str, list[str]] = {
    "greenhouse": ["boards-api.greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io"],
    "lever": ["api.lever.co", "jobs.lever.co"],
    "ashby": ["api.ashbyhq.com", "jobs.ashbyhq.com"],
    "workday": [".myworkdayjobs.com"],
    "amazon": ["www.amazon.jobs"],
    "microsoft": ["gcsservices.careers.microsoft.com"],
    # Platforms served from a shared VENDOR host (company sites are subdomains/vanity domains).
    # These are platform hosts, not per-company — the vanity domain (if any) is still added
    # per-run via EXTRA_ALLOW. In integration these come from each adapter's declared host(s).
    "oracle_cloud": [".oraclecloud.com"],
    "icims": [".icims.com"],
    "smartrecruiters": ["api.smartrecruiters.com"],
    "eightfold": [".eightfold.ai"],
}

# Infra the sandboxed CLI itself needs (its only LLM endpoint).
INFRA_HOSTS: list[str] = ["api.anthropic.com"]


def allowlist_hosts() -> list[str]:
    hosts = {h for hs in SOURCE_HOSTS.values() for h in hs} | set(INFRA_HOSTS)
    return sorted(hosts)


def write_allowlist(path: Path) -> list[str]:
    """(Re)generate the proxy allow-list file from the catalog. Idempotent."""
    hosts = allowlist_hosts()
    lines = [
        "# GENERATED from catalog.py — do not edit by hand.",
        "# = the egress hosts of every supported source + the Anthropic API. The per-run",
        "#   company careers host is added separately via EXTRA_ALLOW (human-approved).",
        "",
        *hosts,
        "",
    ]
    path.write_text("\n".join(lines))
    return hosts


if __name__ == "__main__":
    p = Path(__file__).resolve().parent / "allowlist.txt"
    print("wrote", len(write_allowlist(p)), "hosts ->", p)
