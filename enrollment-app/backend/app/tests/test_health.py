"""GET /api/health — liveness + SQLite check (G1)."""

from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app_version"]
    # Frigate reachability is deliberately null pre-Phase-6 (constitution IV.3).
    assert body["frigate"] == {"reachable": None}


def test_phase6_routes_return_feature_not_enabled(client):
    """Explicit 501 stubs — never fake enrollment (contracts/rest-api.md)."""
    assert client.post("/api/people/00000000-0000-0000-0000-000000000000/enroll").status_code == 501
    assert (
        client.delete("/api/people/00000000-0000-0000-0000-000000000000/enrollment").status_code
        == 501
    )
    assert client.get("/api/frigate/status").status_code == 501
    body = client.get("/api/frigate/status").json()
    assert body["error"]["code"] == "FEATURE_NOT_ENABLED"