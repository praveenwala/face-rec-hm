"""Phase 4 photo quality tests (T022–T028, G4).

Covers the full G4 checklist: detector loading, missing-model explicit failure
(no silent Haar fallback), face count 0/1/>1, face size (accepted + too small),
sharpness (clear + blurred), brightness (normal/underexposed/overexposed),
quality states (SUITABLE/UNSUITABLE/REVIEW_REQUIRED), persistence (measurements
stored, original untouched, no normalized artifact), the approval boundary
(analysis NEVER sets approved), and the enrollment boundary (analysis never
calls Frigate; enrolled_in_frigate stays false; frigate_identity_name stays
null).

Fixtures: the single committed public-domain photo (astronaut.png, see
fixtures/README.md) plus derived images generated at test time (resize,
composite, blur, brightness) and solid-color images for NO_FACE. Never any
household/biometric media.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

from app.exceptions import FaceDetectorUnavailableError
from app.models.enums import QualityStatus, RejectionReason
from app.services.face_detector import FaceDetectionService
from app.services.quality_service import PhotoQualityService
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


def _solid_bytes() -> bytes:
    return _png_bytes(Image.new("RGB", (320, 240), (120, 130, 140)))


def _two_faces_bytes() -> bytes:
    """Two astronauts side by side — YuNet should find exactly 2 faces."""
    astro = _astro()
    comp = Image.new("RGB", (1024, 512), (255, 255, 255))
    comp.paste(astro, (0, 0))
    comp.paste(astro, (512, 0))
    return _png_bytes(comp)


def _tiny_face_bytes() -> bytes:
    """A small (80px) face on a wide 1920x260 canvas — detected but too small."""
    astro = _astro()
    canvas = Image.new("RGB", (1920, 260), (240, 240, 240))
    canvas.paste(astro.resize((80, int(80 * astro.height / astro.width))), (400, 40))
    return _png_bytes(canvas)


def _blurred_bytes() -> bytes:
    return _png_bytes(_astro().filter(ImageFilter.GaussianBlur(8)))


def _dark_bytes() -> bytes:
    """Multiply luminance by 0.25 → face-crop mean ~38 (< BRIGHTNESS_MIN=40)."""
    return _png_bytes(_astro().point(lambda p: int(p * 0.25)))


def _bright_bytes() -> bytes:
    """Add +90 → face-crop mean ~226 (> BRIGHTNESS_MAX=220)."""
    return _png_bytes(_astro().point(lambda p: min(255, p + 90)))


@pytest.fixture()
def person(client):
    resp = client.post(
        "/api/people", json={"display_name": "Quality Tester", "relationship": "Family"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(client, person_id: str, name: str, data: bytes, mime: str = "image/png"):
    resp = client.post(
        f"/api/people/{person_id}/photos",
        files=[("files", (name, data, mime))],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["results"][0]


# ---------------------------------------------------------------- detector


@requires_model
def test_detector_loads_and_finds_astronaut_face(settings):
    """The approved YuNet model loads and detects exactly one face on the fixture."""
    det = FaceDetectionService(settings)
    img = _astro()
    bgr = np.array(img)[:, :, ::-1].copy()
    faces = det.detect(bgr)
    assert len(faces) == 1
    f = faces[0]
    assert f.score >= settings.quality.min_face_detect_score
    assert f.width > 0 and f.height > 0


def test_detector_missing_model_raises_explicit_error_no_fallback(settings):
    """Missing model → explicit FaceDetectorUnavailableError. NO silent Haar
    fallback (user-approved Phase 4 decision): readiness semantics must never
    silently change detector."""
    model_path = settings.facedet_model_path
    # Ensure the model is absent (remove the conftest copy if present) so the
    # detector's own load path is exercised, not a cached/copied one.
    model_path.unlink(missing_ok=True)
    det = FaceDetectionService(settings)
    bgr = np.zeros((480, 640, 3), dtype=np.uint8)
    with pytest.raises(FaceDetectorUnavailableError):
        det.detect(bgr)
    # The failed path must never be cached (i.e. no fallback got loaded under it).
    assert str(model_path) not in FaceDetectionService._detector_cache


# ---------------------------------------------------------------- upload → analysis


@requires_model
def test_upload_suitable_photo(client, person):
    result = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.SUITABLE.value
    assert result["rejection_reason"] is None
    assert result["approved"] is False
    m = result["measurements"]
    assert m["face_count"] == 1
    assert 0.01 < m["face_size_ratio"] < 0.5  # sane size, above FACE_TOO_SMALL floor
    assert m["sharpness"] > 0
    assert 0 < m["brightness"] < 255


@requires_model
def test_upload_no_face_unsuitable(client, person):
    result = _upload(client, person["id"], "blank.png", _solid_bytes())
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.UNSUITABLE.value
    assert result["rejection_reason"] == RejectionReason.NO_FACE.value
    assert result["measurements"]["face_count"] == 0


@requires_model
def test_upload_multiple_faces_review_required(client, person):
    result = _upload(client, person["id"], "two.png", _two_faces_bytes())
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.REVIEW_REQUIRED.value
    assert result["rejection_reason"] == RejectionReason.MULTIPLE_FACES.value
    assert result["measurements"]["face_count"] == 2
    # Hard stop: no auto-selection, no suitability — and the guidance is explicit.
    note = result["rejection_details"]["note"]
    assert "only the intended person" in note


@requires_model
def test_upload_tiny_face_unsuitable(client, person):
    result = _upload(client, person["id"], "tiny.png", _tiny_face_bytes())
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.UNSUITABLE.value
    assert result["rejection_reason"] == RejectionReason.FACE_TOO_SMALL.value
    assert result["measurements"]["face_size_ratio"] < 0.01
    assert result["measurements"]["face_count"] == 1  # detected, but too small


@requires_model
def test_upload_blurry_unsuitable(client, person):
    result = _upload(client, person["id"], "blur.png", _blurred_bytes())
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.UNSUITABLE.value
    assert result["rejection_reason"] == RejectionReason.TOO_BLURRY.value
    assert result["measurements"]["sharpness"] < 40.0


@requires_model
def test_upload_underexposed(client, person):
    result = _upload(client, person["id"], "dark.png", _dark_bytes())
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.UNSUITABLE.value
    assert result["rejection_reason"] == RejectionReason.UNDEREXPOSED.value
    assert result["measurements"]["brightness"] < 40.0


@requires_model
def test_upload_overexposed(client, person):
    result = _upload(client, person["id"], "bright.png", _bright_bytes())
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.UNSUITABLE.value
    assert result["rejection_reason"] == RejectionReason.OVEREXPOSED.value
    assert result["measurements"]["brightness"] > 220.0


# ---------------------------------------------------------------- approval / enrollment boundaries


@requires_model
def test_suitable_photo_never_auto_approved_or_enrolled(client, person, app):
    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]

    detail = client.get(f"/api/people/{person['id']}/photos/{photo_id}").json()
    assert detail["quality_status"] == QualityStatus.SUITABLE.value
    assert detail["approved"] is False
    assert detail["enrolled_in_frigate"] is False
    assert detail["rejection_reason"] is None

    with app.state.session_factory() as session:
        from app.models.photo import EnrollmentPhoto

        row = session.get(EnrollmentPhoto, photo_id)
        assert row.approved is False
        assert row.enrolled_in_frigate is False

    # The person record is untouched by analysis — no identity created.
    p = client.get(f"/api/people/{person['id']}").json()
    assert p["frigate_identity_name"] is None
    assert p["enrollment_status"] in ("DRAFT", "NOT_READY")


@requires_model
def test_analysis_never_calls_frigate(client, person):
    """Analysis must not invoke any Frigate enrollment API. The quality pipeline
    has no Frigate client at all — prove it by asserting no network-capable Frigate
    path exists in the services used by analysis, and that the DB flags stay off."""
    from app.services import face_detector as fd_mod
    from app.services import quality_service as qs_mod

    for mod in (fd_mod, qs_mod):
        assert "frigate" not in {name.lower() for name in dir(mod)}

    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]
    # Explicit re-analysis also stays within the app.
    resp = client.post(f"/api/people/{person['id']}/photos/{photo_id}/analyze")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quality_status"] == QualityStatus.SUITABLE.value
    assert body["enrolled_in_frigate"] is False
    assert body["approved"] is False


# ---------------------------------------------------------------- re-analysis


@requires_model
def test_reanalysis_is_explicit_and_deterministic(client, person):
    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]
    first = client.get(f"/api/people/{person['id']}/photos/{photo_id}").json()

    resp = client.post(f"/api/people/{person['id']}/photos/{photo_id}/analyze")
    assert resp.status_code == 200, resp.text
    second = resp.json()
    assert second["quality_status"] == first["quality_status"] == QualityStatus.SUITABLE.value
    assert second["face_count"] == first["face_count"] == 1
    assert second["face_size_ratio"] == first["face_size_ratio"]
    assert second["approved"] is False and second["enrolled_in_frigate"] is False


@requires_model
def test_reanalysis_corrupt_stored_file_decode_failure(client, person, settings):
    """If the stored original is later corrupted, re-analysis reports
    MEDIA_DECODE_FAILURE — never NO_FACE (FR-016 distinction preserved)."""
    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]
    stored = next(
        (settings.data_dir / "people" / person["id"] / "original").iterdir()
    )
    stored.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"corrupted")

    resp = client.post(f"/api/people/{person['id']}/photos/{photo_id}/analyze")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quality_status"] == QualityStatus.UNSUITABLE.value
    assert body["rejection_reason"] == RejectionReason.MEDIA_DECODE_FAILURE.value


@requires_model
def test_analyze_cross_person_blocked(client, person):
    other = client.post(
        "/api/people", json={"display_name": "Other", "relationship": "Friend"}
    ).json()
    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]
    resp = client.post(f"/api/people/{other['id']}/photos/{photo_id}/analyze")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PHOTO_NOT_FOUND"


@requires_model
def test_analyze_malformed_uuid_400(client, person):
    resp = client.post(f"/api/people/{person['id']}/photos/not-a-uuid/analyze")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- missing-model behavior


def test_upload_with_missing_model_degrades_cleanly(client, person, settings):
    """Detector unavailable → upload still succeeds and stores the photo, quality
    stays PENDING with an explicit analysis_error. No fabricated classification."""
    settings.facedet_model_path.unlink(missing_ok=True)

    result = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))
    assert result["photo_id"] is not None
    assert result["quality_status"] == QualityStatus.PENDING.value
    assert result["rejection_reason"] is None
    assert result["analysis_error"] == "FACE_DETECTOR_UNAVAILABLE"
    assert result["approved"] is False

    photos = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    assert len(photos) == 1
    assert photos[0]["quality_status"] == QualityStatus.PENDING.value


def test_analyze_missing_model_returns_503(client, person, settings):
    settings.facedet_model_path.unlink(missing_ok=True)
    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]

    resp = client.post(f"/api/people/{person['id']}/photos/{photo_id}/analyze")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "FACE_DETECTOR_UNAVAILABLE"


# ---------------------------------------------------------------- persistence / privacy


@requires_model
def test_measurements_persisted_original_untouched(app, client, person, settings):
    original = _png_bytes(_astro())
    photo_id = _upload(client, person["id"], "astro.png", original)["photo_id"]

    # Original served byte-for-byte after analysis ran (FR-011).
    resp = client.get(f"/api/people/{person['id']}/photos/{photo_id}/file")
    assert resp.content == original

    # DB holds measurements, never bytes, and no normalized/approved copies exist.
    with app.state.session_factory() as session:
        from app.models.photo import EnrollmentPhoto

        row = session.get(EnrollmentPhoto, photo_id)
        assert row.face_count == 1
        assert row.face_size_ratio and row.face_size_ratio > 0.01
        assert row.sharpness and row.sharpness > 0
        assert row.brightness and 0 < row.brightness < 255
        assert row.measurements["face_count"] == 1
        assert row.storage_path.startswith(f"people/{person['id']}/original/")

    person_dir = settings.data_dir / "people" / person["id"]
    assert not (person_dir / "normalized").exists() or not list(
        (person_dir / "normalized").iterdir()
    )
    assert not (person_dir / "approved").exists()

    # kind=normalized stays an honest 404 — no normalized artifact in this phase.
    resp = client.get(
        f"/api/people/{person['id']}/photos/{photo_id}/file", params={"kind": "normalized"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PHOTO_NOT_FOUND"


# ---------------------------------------------------------------- phase 3 surface intact


@requires_model
def test_preview_delete_still_work_on_analyzed_photo(client, person, settings):
    photo_id = _upload(client, person["id"], "astro.png", _png_bytes(_astro()))["photo_id"]

    thumb = client.get(f"/api/people/{person['id']}/photos/{photo_id}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(thumb.content)) as t:
        assert max(t.size) <= 300

    person_dir = settings.data_dir / "people" / person["id"]
    assert list((person_dir / "original").iterdir())

    assert client.delete(f"/api/people/{person['id']}/photos/{photo_id}").status_code == 204
    assert not (person_dir / "original").exists() or not list(
        (person_dir / "original").iterdir()
    )
    assert client.get(f"/api/people/{person['id']}/photos").json()["photos"] == []


# ---------------------------------------------------------------- classification precedence


@requires_model
def test_classification_precedence_documented(client, person):
    """The pipeline applies precedence deterministically (contract
    photo-quality.md): decode → NO_FACE → MULTIPLE_FACES → FACE_TOO_SMALL →
    TOO_BLURRY → exposure → SUITABLE. A multi-fault image reports its primary
    reason while retaining full measurements."""
    # Multi-face wins over any single-face measurement issue that might also exist.
    result = _upload(client, person["id"], "two.png", _two_faces_bytes())
    assert result["rejection_reason"] == RejectionReason.MULTIPLE_FACES.value
    assert result["measurements"]["face_count"] == 2
    # No-face fixture carries no sharpness/brightness claims.
    blank = _upload(client, person["id"], "blank2.png", _solid_bytes())
    assert blank["rejection_reason"] == RejectionReason.NO_FACE.value
    assert "sharpness" not in blank["measurements"]