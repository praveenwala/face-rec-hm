"""Localhost-only binding (spec FR-002, SC-011, G1)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
RUN_SH = BACKEND_DIR / "run.sh"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_run_sh_binds_loopback_only():
    content = RUN_SH.read_text()
    assert "--host 127.0.0.1" in content, "run.sh must bind 127.0.0.1"
    assert "--port 8000" in content
    assert "0.0.0.0" not in content, "run.sh must never bind 0.0.0.0"


def test_uvicorn_subprocess_serves_health_on_loopback(tmp_path):
    """Boot a real uvicorn process on 127.0.0.1 and hit /api/health."""
    port = _free_port()
    env = dict(os.environ)
    env["ENROLLMENT_DATA_DIR"] = str(tmp_path / "data")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        url = f"http://127.0.0.1:{port}/api/health"
        last_error = None
        for _ in range(40):
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace")
                pytest_fail = AssertionError(f"uvicorn exited early:\n{out}")
                raise pytest_fail
            try:
                with urllib.request.urlopen(url, timeout=1) as resp:
                    assert resp.status == 200
                    body = json.loads(resp.read().decode())
                    assert body["status"] == "ok"
                    assert body["database"] == "ok"
                    break
            except Exception as exc:  # noqa: BLE001 — retry loop
                last_error = exc
                time.sleep(0.25)
        else:
            raise AssertionError(f"health endpoint never became ready: {last_error}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_health_via_testclient_ok(client):
    assert client.get("/api/health").status_code == 200