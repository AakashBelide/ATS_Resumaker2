"""Phase-A containment eval — proves the sandbox is secure BEFORE we ever put an agent in it.

Runs plain shell probes inside the locked-down box and asserts:
  1. non-root                         (uid == 10001)
  2. allow-listed egress works        (curl greenhouse API -> 200, proxy logs ALLOW)
  3. non-allow-listed egress blocked  (curl example.com -> not 200, proxy logs DENY)
  4. per-run host allow-list works    (EXTRA_ALLOW=example.com -> now reachable)
  5. no secrets/source in the box     (no .env, no `resumaker` paths anywhere on the FS)
  6. write confinement                (/work writable tmpfs; rootfs read-only)

Run:  python pocs/agentic_onboard/eval/containment_test.py
Exit code 0 = all pass. Requires Docker.
"""
from __future__ import annotations

import sys
from pathlib import Path

from resumaker.onboarding.sandbox import runner  # noqa: E402

PROBE = r"""
set +e
echo "UID=$(id -u)"
echo "WORKLS=[$(ls -A /work 2>/dev/null | tr '\n' ' ')]"
echo "ALLOW_CURL=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 https://boards-api.greenhouse.io/v1/boards/stripe)"
echo "DENY_CURL=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 https://example.com 2>/dev/null)"
echo "ENV_HITS=[$(find / -name '.env' 2>/dev/null | head -n 3 | tr '\n' ' ')]"
echo "SRC_HITS=[$(find / -path '*resumaker*' 2>/dev/null | head -n 3 | tr '\n' ' ')]"
touch /work/ok 2>/dev/null && echo "WORK_WRITE=ok"
echo "ETC_WRITE=$(touch /etc/x 2>&1)"
"""

EXTRA_PROBE = r"""
echo "EXTRA_CURL=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 https://example.com 2>/dev/null)"
"""


def kv(stdout: str) -> dict[str, str]:
    out = {}
    for line in stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    print("building sandbox images (first run compiles; cached after)…", flush=True)
    runner.build()

    print("run 1/2 — default allow-list probe…", flush=True)
    r1 = runner.run(["sh", "-c", PROBE], timeout=180)
    v = kv(r1.stdout)
    print("run 2/2 — per-run EXTRA_ALLOW=example.com probe…", flush=True)
    r2 = runner.run(["sh", "-c", EXTRA_PROBE], extra_allow="example.com", timeout=120)
    v2 = kv(r2.stdout)

    checks: list[tuple[str, bool, str]] = [
        ("non-root (uid 10001)", v.get("UID") == "10001", f"UID={v.get('UID')}"),
        ("/work starts empty", v.get("WORKLS") == "[]", f"WORKLS={v.get('WORKLS')}"),
        ("allow-listed egress -> 200", v.get("ALLOW_CURL") == "200", f"ALLOW_CURL={v.get('ALLOW_CURL')}"),
        ("proxy logged ALLOW greenhouse", "ALLOW boards-api.greenhouse.io" in r1.proxy_log, "proxy_log"),
        ("blocked egress != 200", v.get("DENY_CURL") not in ("200",), f"DENY_CURL={v.get('DENY_CURL')}"),
        ("proxy logged DENY example.com", "DENY example.com" in r1.proxy_log, "proxy_log"),
        ("no .env anywhere in box", v.get("ENV_HITS") == "[]", f"ENV_HITS={v.get('ENV_HITS')}"),
        ("no resumaker source in box", v.get("SRC_HITS") == "[]", f"SRC_HITS={v.get('SRC_HITS')}"),
        ("/work writable (tmpfs)", v.get("WORK_WRITE") == "ok", f"WORK_WRITE={v.get('WORK_WRITE')}"),
        ("rootfs read-only", "Read-only file system" in v.get("ETC_WRITE", ""), f"ETC_WRITE={v.get('ETC_WRITE')}"),
        ("per-run EXTRA_ALLOW opens host", v2.get("EXTRA_CURL") == "200", f"EXTRA_CURL={v2.get('EXTRA_CURL')}"),
        ("proxy logged ALLOW example.com (run2)", "ALLOW example.com" in r2.proxy_log, "proxy_log"),
    ]

    print("\n=== containment results ===")
    ok = True
    for name, passed, evidence in checks:
        mark = "PASS" if passed else "FAIL"
        if not passed:
            ok = False
        print(f"  [{mark}] {name}  ({evidence})")

    if not ok:
        print("\nFAILED — sandbox is not containing as expected. See evidence above.")
        print("--- last agent stdout ---\n" + r1.stdout)
        print("--- proxy log (run1) ---\n" + r1.proxy_log)
    else:
        print("\nALL CONTAINMENT CHECKS PASSED — the box is non-root, read-only, "
              "secret-free, and can only reach allow-listed hosts.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
