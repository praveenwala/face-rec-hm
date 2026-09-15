"""Observable contract tests for the production Frigate HTTP transport.

All requests use httpx.MockTransport.  These tests never contact a Frigate
instance and never submit a biometric image.
"""

from __future__ import annotations

import json

import httpx

from app.config import FrigateConfig
from app.services.frigate_http_transport import HttpxFrigateTransport


def test_reads_faces_from_configured_target_url():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    transport = HttpxFrigateTransport(
        FrigateConfig(api_url="http://frigate.example:5001"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    status, body = transport.request("GET", "/api/faces")

    assert (status, body) == (200, {})
    assert str(seen[0].url) == "http://frigate.example:5001/api/faces"


def test_retries_after_auth_challenge_with_env_configured_credentials():
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        if request.url.path == "/api/faces" and len(calls) == 1:
            return httpx.Response(401, json={"message": "authentication required"})
        if request.url.path == "/api/login":
            assert json.loads(request.content) == {"user": "runtime-user", "password": "runtime-password"}
            return httpx.Response(200, headers={"set-cookie": "frigate_token=session; Path=/"})
        assert request.headers.get("cookie") == "frigate_token=session"
        return httpx.Response(200, json={})

    transport = HttpxFrigateTransport(
        FrigateConfig(
            api_url="http://frigate.example:5001",
            auth_username="runtime-user",
            auth_password="runtime-password",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert transport.request("GET", "/api/faces") == (200, {})
    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/api/faces"),
        ("POST", "/api/login"),
        ("GET", "/api/faces"),
    ]
