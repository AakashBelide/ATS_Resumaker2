#!/usr/bin/env python3
"""Egress allow-list proxy for the onboarding sandbox.

The sandbox container has NO direct internet (it sits on an `internal: true` Docker network);
its ONLY route out is this proxy. We permit `CONNECT` (https) and absolute-URI http ONLY to
allow-listed hosts and return 403 for everything else. This is the containment crux: even a
fully hijacked agent (prompt-injected via a scraped careers page) cannot exfiltrate data or
call home, because every packet it emits must pass this allow-list.

Host matching supports exact hosts and leading-dot suffix wildcards:
  ".myworkdayjobs.com" matches "acme.wd1.myworkdayjobs.com".

Allow-list sources (union): the file at EGRESS_ALLOWLIST_FILE (default /etc/egress/allowlist.txt),
the EGRESS_ALLOWLIST env (comma-sep), and EXTRA_ALLOW env (comma-sep, used to add the specific
company careers host per run). Stdlib only — no third-party deps in the proxy image.
"""
from __future__ import annotations

import contextlib
import http.client
import os
import select
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def _load_allowlist() -> set[str]:
    hosts: set[str] = set()
    for env in ("EGRESS_ALLOWLIST", "EXTRA_ALLOW"):
        for h in os.environ.get(env, "").split(","):
            h = h.strip().lower()
            if h:
                hosts.add(h)
    path = os.environ.get("EGRESS_ALLOWLIST_FILE", "/etc/egress/allowlist.txt")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.split("#", 1)[0].strip().lower()
                if line:
                    hosts.add(line)
    return hosts


ALLOW = _load_allowlist()


def _allowed(host: str | None) -> bool:
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    for a in ALLOW:
        if a.startswith("."):
            if host == a[1:] or host.endswith(a):
                return True
        elif host == a:
            return True
    return False


def _log(decision: str, host: str) -> None:
    # One line per decision on stderr — the containment eval asserts on these.
    print(f"{decision} {host}", file=sys.stderr, flush=True)


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _deny(self, host: str) -> None:
        _log("DENY", host)
        body = b"egress blocked by allowlist"
        self.send_response(403)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    # ---- https (the common path): CONNECT tunnel, host from the CONNECT line ----
    def do_CONNECT(self) -> None:
        host = self.path.rsplit(":", 1)[0]
        port = int(self.path.rsplit(":", 1)[1]) if ":" in self.path else 443
        if not _allowed(host):
            return self._deny(host)
        try:
            upstream = socket.create_connection((host, port), timeout=15)
        except OSError:
            self.send_response(502)
            self.send_header("Connection", "close")
            self.end_headers()
            return
        _log("ALLOW", host)
        self.send_response(200, "Connection established")
        self.end_headers()
        self._tunnel(self.connection, upstream)

    def _tunnel(self, a: socket.socket, b: socket.socket) -> None:
        try:
            while True:
                r, _, x = select.select([a, b], [], [a, b], 60)
                if x or not r:
                    break
                for s in r:
                    data = s.recv(65536)
                    if not data:
                        return
                    (b if s is a else a).sendall(data)
        finally:
            for s in (a, b):
                with contextlib.suppress(OSError):
                    s.close()

    # ---- plain http (rare): absolute-URI forward, allow-listed ----
    def _forward_http(self) -> None:
        u = urlsplit(self.path)
        if not _allowed(u.hostname):
            return self._deny(u.hostname or self.path)
        _log("ALLOW", u.hostname or "")
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None
        try:
            conn = http.client.HTTPConnection(u.hostname or "", u.port or 80, timeout=15)
            path = u.path + (("?" + u.query) if u.query else "")
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in ("proxy-connection", "connection")}
            conn.request(self.command, path or "/", body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except OSError:
            self.send_response(502)
            self.send_header("Connection", "close")
            self.end_headers()
            return
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in ("transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    do_GET = _forward_http
    do_POST = _forward_http
    do_HEAD = _forward_http

    def log_message(self, *args) -> None:  # silence default request logging
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PROXY_PORT", "8080"))
    print(f"egress proxy on :{port}; allow={sorted(ALLOW)}", file=sys.stderr, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Proxy).serve_forever()
