"""Phase 5 enrollment-readiness tests (T029–T033, G5).

Covers the full G5 checklist: explicit approval (SUITABLE only, idempotent,
cross-person blocked), unapproval, the >= 5 approved-suitable gate, exact
duplicate protection (one credit per SHA-256 group), readiness recalculation on
delete/unapprove/reanalysis, reanalysis approval-clearing, detector-failure
preservation, READY-never-enrolls isolation, and audit events
(PHOTO_APPROVED / PHOTO_UNAPPROVED / READINESS_CHANGED only on transitions).

Fixtures: the single committed public-domain astronaut.png + derived synthetic
variants (resize/brightness). Never household/biometric media.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image

from app.models.enums import AuditAction, QualityStatus, RejectionReason
from app.tests.conftest import MODEL_AVAILABLE

requires_model = pytest.mark.skipif(
    not MODEL_AVAILABLE,
    reason="face-detection model not fetched — run scripts/fetch_models.sh",
)

FIXTURE = Path(__file__).parent / "fixtures" / "astronaut.png"


# ---------------------------------------------------------------- fixtures


def _astro() -> Image.Image:
    return Image.open(FIXTURE).convert("RGB")


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _suitable_variants() -> list[bytes]:
    """5 distinct, all-SUITABLE images (distinct sha256; see G5 duplicate tests)."""
    astro = _astro()
    return [
        _png_bytes(astro),
        _png_bytes(astro.resize((400, 400))),
        _png_bytes(astro.resize((600, 600))),
        _png_bytes(astro.point(lambda p: min(255, p + 10))),
        _png_bytes(astro.point(lambda p: max(0, p - 10))),
    ]


def _solid_bytes() -> bytes:
    """No-face fixture → UNSUITABLE (NO_FACE)."""
    return _png_bytes(Image.new("RGB", (320, 240), (120, 130, 140)))


def _two_faces_bytes() -> bytes:
    """Two-face fixture → REVIEW_REQUIRED (MULTIPLE_FACES)."""
    astro = _astro()
    comp = Image.new("RGB", (1024, 512), (255, 255, 255))
    comp.paste(astro, (0, 0))
    comp.paste(astro, (512, 0))
    return _png_bytes(comp)


@pytest.fixture()
def person(client):
    resp = client.post(
        "/api/people", json={"display_name": "Ready Tester", "relationship": "Family"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(client, person_id: str, name: str, data: bytes) -> str:
    resp = client.post(
        f"/api/people/{person_id}/photos",
        files=[("files", (name, data, "image/png"))],
    )
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is not None, result
    return result["photo_id"]


def _approve(client, person_id: str, photo_id: str):
    return client.post(f"/api/people/{person_id}/photos/{photo_id}/approve")


def _unapprove(client, person_id: str, photo_id: str):
    return client.post(f"/api/people/{person_id}/photos/{photo_id}/unapprove")


def _readiness(client, person_id: str) -> dict:
    resp = client.get(f"/api/people/{person_id}/readiness")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _audit(client) -> list[dict]:
    return client.get("/api/audit").json()["entries"]


# ---------------------------------------------------------------- approval


@requires_model
def test_approve_suitable_photo(client, person):
    photo_id = _upload(client, person["id"], "a.png", _suitable_variants()[0])
    detail = _approve(client, person["id"], photo_id)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["approved"] is True
    assert body["quality_status"] == QualityStatus.SUITABLE.value  # unchanged
    assert body["enrolled_in_frigate"] is False


@requires_model
def test_approve_unsuitable_rejected(client, person):
    photo_id = _upload(client, person["id"], "blank.png", _solid_bytes())
    assert _readiness(client, person["id"])["status"] == "NOT_READY"
    resp = _approve(client, person["id"], photo_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PHOTO_NOT_APPROVABLE"
    assert resp.json()["error"]["details"]["quality_status"] == QualityStatus.UNSUITABLE.value


@requires_model
def test_approve_review_required_rejected(client, person):
    photo_id = _upload(client, person["id"], "two.png", _two_faces_bytes())
    resp = _approve(client, person["id"], photo_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PHOTO_NOT_APPROVABLE"
    assert resp.json()["error"]["details"]["quality_status"] == QualityStatus.REVIEW_REQUIRED.value


def test_approve_pending_rejected(client, person, settings):
    """PENDING occurs only when the detector is unavailable; approval must refuse it."""
    settings.facedet_model_path.unlink(missing_ok=True)
    photo_id = _upload(client, person["id"], "a.png", _suitable_variants()[0])
    resp = _approve(client, person["id"], photo_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PHOTO_NOT_APPROVABLE"
    assert resp.json()["error"]["details"]["quality_status"] == QualityStatus.PENDING.value


@requires_model
def test_approve_idempotent_no_duplicate_audit(client, person):
    photo_id = _upload(client, person["id"], "a.png", _suitable_variants()[0])
    assert _approve(client, person["id"], photo_id).status_code == 200
    assert _approve(client, person["id"], photo_id).status_code == 200
    approved_events = [
        e for e in _audit(client) if e["action"] == AuditAction.PHOTO_APPROVED.value
    ]
    assert len(approved_events) == 1


@requires_model
def test_unapprove_works_and_recalculates(client, person):
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"

    resp = _unapprove(client, person["id"], ids[0])
    assert resp.status_code == 200
    assert resp.json()["approved"] is False
    assert resp.json()["quality_status"] == QualityStatus.SUITABLE.value  # analysis untouched
    readiness = _readiness(client, person["id"])
    assert readiness["status"] == "NOT_READY"
    assert readiness["approved_suitable_count"] == 4

    # unapprove again = idempotent no-op
    assert _unapprove(client, person["id"], ids[0]).status_code == 200
    assert _readiness(client, person["id"])["approved_suitable_count"] == 4


@requires_model
def test_cross_person_approval_blocked(client, person):
    other = client.post(
        "/api/people", json={"display_name": "Other", "relationship": "Friend"}
    ).json()
    photo_id = _upload(client, person["id"], "a.png", _suitable_variants()[0])
    assert _approve(client, other["id"], photo_id).status_code == 404
    assert _unapprove(client, other["id"], photo_id).status_code == 404
    # The photo is untouched and unapproved.
    detail = client.get(f"/api/people/{person['id']}/photos/{photo_id}").json()
    assert detail["approved"] is False


# ---------------------------------------------------------------- readiness


@requires_model
def test_readiness_counts_and_floor(client, person):
    assert _readiness(client, person["id"])["status"] == "DRAFT"
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]

    # 0 approved → NOT_READY even with 5 suitable
    r = _readiness(client, person["id"])
    assert r["status"] == "NOT_READY"
    assert r["approved_suitable_count"] == 0
    assert r["suitable_count"] == 5  # total SUITABLE regardless of approval
    assert r["total_uploaded"] == 5
    assert r["minimum_required"] == 5 and r["remaining_required"] == 5

    # 4 approved → NOT_READY
    for pid in ids[:4]:
        assert _approve(client, person["id"], pid).status_code == 200
    r = _readiness(client, person["id"])
    assert r["status"] == "NOT_READY"
    assert r["approved_suitable_count"] == 4
    assert r["remaining_required"] == 1
    assert r["approved_count"] == 4

    # 5th approved → READY
    assert _approve(client, person["id"], ids[4]).status_code == 200
    r = _readiness(client, person["id"])
    assert r["status"] == "READY"
    assert r["approved_suitable_count"] == 5
    assert r["remaining_required"] == 0
    assert r["enrollment_enabled"] is False
    assert r["missing"] == []

    # person summary reflects the gate too
    summary = client.get(f"/api/people/{person['id']}").json()
    assert summary["enrollment_status"] == "READY"
    assert summary["suitable_count"] == 5


@requires_model
def test_readiness_ignores_unsuitable_and_review(client, person):
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    unsuitable_id = _upload(client, person["id"], "blank.png", _solid_bytes())
    review_id = _upload(client, person["id"], "two.png", _two_faces_bytes())
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200

    r = _readiness(client, person["id"])
    assert r["status"] == "READY"
    assert r["approved_suitable_count"] == 5
    assert r["unsuitable_count"] == 1
    assert r["review_required_count"] == 1
    # They never count, but remain listed and unapproved.
    assert client.get(f"/api/people/{person['id']}/photos/{unsuitable_id}").json()["approved"] is False
    assert client.get(f"/api/people/{person['id']}/photos/{review_id}").json()["approved"] is False


@requires_model
def test_delete_approved_photo_recalculates_readiness(client, person, settings):
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"

    assert client.delete(f"/api/people/{person['id']}/photos/{ids[0]}").status_code == 204
    r = _readiness(client, person["id"])
    assert r["status"] == "NOT_READY"
    assert r["approved_suitable_count"] == 4
    assert r["total_uploaded"] == 4

    # Re-upload + approve a fresh distinct image → READY again (no stale state).
    fresh = _upload(client, person["id"], "new.png", _png_bytes(_astro().resize((480, 480))))
    assert _approve(client, person["id"], fresh).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"


@requires_model
def test_unapprove_one_of_five_returns_not_ready(client, person):
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"
    assert _unapprove(client, person["id"], ids[0]).status_code == 200
    assert _readiness(client, person["id"])["status"] == "NOT_READY"
    # Reapprove the fifth → READY (user rule: adding/reapproving fifth → READY)
    assert _approve(client, person["id"], ids[0]).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"


# ---------------------------------------------------------------- duplicates


@requires_model
def test_near_duplicate_set_can_still_reach_ready(client, person):
    """Five visually-similar (pHash-close) but byte-distinct suitable photos,
    explicitly approved, MAY reach READY — similarity is advisory only (user's
    Phase 5 near-duplicate example). The hard gate is exactly-duplicate-deduped
    approval, never visual variety."""
    variants = _suitable_variants()
    assert len({hashlib.sha256(v).hexdigest() for v in variants}) == 5  # byte-distinct
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(variants)]
    # Confirm they are mutually near-duplicates (advisory fires), yet SUITABLE.
    for pid in ids:
        d = client.get(f"/api/people/{person['id']}/photos/{pid}").json()
        assert d["quality_status"] == QualityStatus.SUITABLE.value
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    r = _readiness(client, person["id"])
    assert r["approved_suitable_count"] == 5
    assert r["status"] == "READY"  # advisory never downgrades READY
    assert r["near_duplicate_advisory"] is True  # UI shows the variety recommendation


@requires_model
def test_exact_duplicate_uploads_cannot_inflate_readiness(client, person):
    """The same bytes uploaded 5 times must NOT yield 5 readiness credits."""
    same = _suitable_variants()[0]
    ids = [_upload(client, person["id"], f"dup{i}.png", same) for i in range(5)]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200

    r = _readiness(client, person["id"])
    assert r["approved_suitable_count"] == 1  # one credit per duplicate group
    assert r["status"] == "NOT_READY"
    assert r["total_uploaded"] == 5

    # Mixing 4 distinct + 2 copies of one of them still only counts 5 credits.
    ids2 = [_upload(client, person["id"], f"x{i}.png", data) for i, data in enumerate(_suitable_variants())]
    # ids2 includes the same bytes as ids[0]; approve all 6 → still 5 credits max.
    for pid in ids2:
        assert _approve(client, person["id"], pid).status_code == 200
    r = _readiness(client, person["id"])
    assert r["approved_suitable_count"] == 5
    assert r["status"] == "READY"  # 5 distinct groups → READY (duplicates didn't inflate but didn't block)


@requires_model
def test_near_duplicate_is_advisory_only(client, person):
    """pHash-close images get advisory metadata but keep SUITABLE and count
    (user's Phase 5 rules #16/#18: advisory MUST NOT replace SUITABLE with
    REVIEW_REQUIRED, MUST NOT block approval, MUST NOT silently approve)."""
    base = _suitable_variants()[0]
    near = _png_bytes(_astro().point(lambda p: min(255, p + 3)))  # pHash-close, different bytes
    pid1 = _upload(client, person["id"], "base.png", base)
    pid2 = _upload(client, person["id"], "near.png", near)

    d1 = client.get(f"/api/people/{person['id']}/photos/{pid1}").json()
    d2 = client.get(f"/api/people/{person['id']}/photos/{pid2}").json()
    # BOTH retain SUITABLE — near similarity alone is never a quality failure.
    assert d1["quality_status"] == QualityStatus.SUITABLE.value
    assert d2["quality_status"] == QualityStatus.SUITABLE.value
    assert d1["rejection_reason"] is None
    assert d2["rejection_reason"] is None

    # Advisory metadata visible (distance/threshold/photo reference) — and the
    # advisory MUST NOT silently approve: both remain approved=false until the
    # user explicitly approves (rule: advisory does not silently approve).
    advisory = (d2["measurements"] or {}).get("near_duplicate_advisory")
    assert advisory is not None
    assert advisory["distance"] <= 8
    assert advisory["photo_id"] == pid1
    s1 = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    by_id = {p["id"]: p for p in s1}
    assert by_id[pid1]["approved"] is False and by_id[pid2]["approved"] is False
    assert by_id[pid2]["near_duplicate"] is not None  # advisory surfaced in summary

    # Advisory never blocks approval: the user MAY approve both, and both count
    # toward the hard gate (near-duplicate ≠ quality failure — user rule #18).
    assert _approve(client, person["id"], pid1).status_code == 200
    assert _approve(client, person["id"], pid2).status_code == 200
    r = _readiness(client, person["id"])
    assert r["approved_suitable_count"] == 2
    assert r["near_duplicate_advisory"] is True  # advisory flag, NOT a downgrade


# ---------------------------------------------------------------- reanalysis safety


@requires_model
def test_reanalysis_degrade_clears_approval(app, client, person, settings):
    """SUITABLE + approved → reanalysis makes it UNSUITABLE → approval cleared,
    readiness recalculated, audit PHOTO_UNAPPROVED (+ READINESS_CHANGED if it flips)."""
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"

    # Corrupt the stored original OF ids[0] specifically (via its storage_path).
    with app.state.session_factory() as session:
        from app.models.photo import EnrollmentPhoto

        row = session.get(EnrollmentPhoto, ids[0])
    stored = settings.data_dir / row.storage_path
    stored.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"corrupted")
    resp = client.post(f"/api/people/{person['id']}/photos/{ids[0]}/analyze")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quality_status"] == QualityStatus.UNSUITABLE.value
    assert body["approved"] is False  # cleared automatically
    assert body["rejection_reason"] == RejectionReason.MEDIA_DECODE_FAILURE.value

    r = _readiness(client, person["id"])
    assert r["approved_suitable_count"] == 4
    assert r["status"] == "NOT_READY"

    events = [e["action"] for e in _audit(client)]
    assert AuditAction.PHOTO_UNAPPROVED.value in events
    assert AuditAction.READINESS_CHANGED.value in events  # READY → NOT_READY transition


@requires_model
def test_reanalysis_detector_failure_preserves_prior_state(client, person, settings):
    """Detector temporarily unavailable during reanalysis must NOT destroy prior
    quality/approval; no accidental readiness transition."""
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    assert _readiness(client, person["id"])["status"] == "READY"

    settings.facedet_model_path.unlink(missing_ok=True)
    # Drop the in-process detector cache so the missing file is actually re-tried
    # (otherwise the already-loaded detector object would mask the outage).
    from app.services.face_detector import FaceDetectionService

    FaceDetectionService._detector_cache.pop(str(settings.facedet_model_path), None)
    resp = client.post(f"/api/people/{person['id']}/photos/{ids[0]}/analyze")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "FACE_DETECTOR_UNAVAILABLE"

    # Prior state fully preserved.
    detail = client.get(f"/api/people/{person['id']}/photos/{ids[0]}").json()
    assert detail["quality_status"] == QualityStatus.SUITABLE.value
    assert detail["approved"] is True
    r = _readiness(client, person["id"])
    assert r["status"] == "READY"
    assert r["approved_suitable_count"] == 5
    # No misleading readiness transition or unapprove audit.
    events = [e["action"] for e in _audit(client)]
    assert AuditAction.PHOTO_UNAPPROVED.value not in events


# ---------------------------------------------------------------- READY never enrolls


@requires_model
def test_ready_never_enrolls(client, person, app):
    ids = [_upload(client, person["id"], f"v{i}.png", data) for i, data in enumerate(_suitable_variants())]
    for pid in ids:
        assert _approve(client, person["id"], pid).status_code == 200
    r = _readiness(client, person["id"])
    assert r["status"] == "READY"

    # Zero enrollment side effects: no identity, no Frigate flags, no enrollment audit.
    p = client.get(f"/api/people/{person['id']}").json()
    assert p["frigate_identity_name"] is None
    assert p["enrollment_status"] == "READY"  # readiness only — never ENROLLED

    with app.state.session_factory() as session:
        from app.models.photo import EnrollmentPhoto

        rows = session.query(EnrollmentPhoto).filter(EnrollmentPhoto.person_id == person["id"]).all()
        assert all(not row.enrolled_in_frigate for row in rows)

    events = [e["action"] for e in _audit(client)]
    assert not any(
        a.startswith("ENROLLMENT_") for a in events if isinstance(a, str)
    )
    # READY transition itself IS audited (NOT_READY → READY).
    ready_events = [e for e in _audit(client) if e["action"] == AuditAction.READINESS_CHANGED.value]
    transitions = [((e["details"] or {}).get("from"), (e["details"] or {}).get("to")) for e in ready_events]
    assert ("NOT_READY", "READY") in transitions

    # Phase 6 endpoint remains an honest 501.
    resp = client.post(f"/api/people/{person['id']}/enroll")
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


# ---------------------------------------------------------------- audit hygiene


@requires_model
def test_approval_audit_metadata_only(client, person):
    photo_id = _upload(client, person["id"], "a.png", _suitable_variants()[0])
    assert _approve(client, person["id"], photo_id).status_code == 200
    assert _unapprove(client, person["id"], photo_id).status_code == 200

    for e in _audit(client):
        details = e["details"] or {}
        for v in details.values():
            assert not isinstance(v, bytes)
            assert "people/" not in str(v)  # no private paths
            assert "app.db" not in str(v)
    approved = next(e for e in _audit(client) if e["action"] == AuditAction.PHOTO_APPROVED.value)
    assert set((approved["details"] or {}).keys()) == {"person_id", "quality_status"}
    unapproved = next(e for e in _audit(client) if e["action"] == AuditAction.PHOTO_UNAPPROVED.value)
    assert set((unapproved["details"] or {}).keys()) == {"person_id", "quality_status"}