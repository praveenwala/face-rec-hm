"""Phase 3 photo ingestion/lifecycle tests (T021, G3).

Covers the full checklist from the approved Phase 3 instructions: valid uploads
(JPEG/PNG/WEBP), decode/format failures kept distinct, oversized files, traversal
and weird filenames, multi-file mixed batches, cross-person access blocking,
preview/file serving without path leakage, delete (DB + files), missing-file
safety, privacy (files under data root only, no bytes in DB), audit events, and
the Phase 3 boundary (PENDING only, no quality analysis, no enrollment).

All media is generated synthetically with Pillow — never household photos.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.models.enums import AuditAction, QualityStatus

# Phase 4: analysis is automatic on upload. The solid-color fixtures below have no
# face, so they classify NO_FACE/UNSUITABLE once analyzed; without the fetched model
# uploads stay PENDING (analysis degrades cleanly). These assertions need the model.
from app.tests.conftest import MODEL_AVAILABLE

requires_model = pytest.mark.skipif(
    not MODEL_AVAILABLE,
    reason="face-detection model not fetched — run scripts/fetch_models.sh",
)

# ---------------------------------------------------------------- fixtures


def _jpeg_bytes(width: int = 640, height: int = 480, color: tuple = (120, 130, 140)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes(width: int = 320, height: int = 240) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 200, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _webp_bytes(width: int = 200, height: int = 150) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 20, 30)).save(buf, format="WEBP")
    return buf.getvalue()


def _gif_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 90), (30, 160, 200)).save(buf, format="GIF")
    return buf.getvalue()


def _bmp_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), (5, 5, 5)).save(buf, format="BMP")
    return buf.getvalue()


def _tiff_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (140, 100), (200, 200, 10)).save(buf, format="TIFF")
    return buf.getvalue()


def _corrupt_jpeg() -> bytes:
    """JPEG magic bytes followed by garbage — Pillow cannot decode it."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"not a real jpeg"


def _fake_jpg_text() -> bytes:
    """A text file renamed .jpg — no image magic at all."""
    return b"this is definitely not an image, just some plain text"


def _heic_magic() -> bytes:
    """Minimal ftyp-box payload claiming the HEIC brand (content sniff only)."""
    return b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1"


@pytest.fixture()
def person(client):
    resp = client.post("/api/people", json={"display_name": "Photo Tester", "relationship": "Family"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(client, person_id: str, files: list[tuple[str, bytes, str]]):
    return client.post(
        f"/api/people/{person_id}/photos",
        files=[("files", (name, data, mime)) for name, data, mime in files],
    )


# ---------------------------------------------------------------- valid uploads


@requires_model
def test_upload_valid_jpeg_stored_and_listed(client, person, settings):
    jpeg = _jpeg_bytes()
    resp = _upload(client, person["id"], [("portrait.jpg", jpeg, "image/jpeg")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is not None
    # Phase 4: automatic analysis — this solid-color fixture has no face.
    assert result["quality_status"] == QualityStatus.UNSUITABLE.value
    assert result["rejection_reason"] == "NO_FACE"
    assert result["approved"] is False

    listing = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    assert len(listing) == 1
    p = listing[0]
    assert p["id"] == result["photo_id"]
    assert p["original_filename"] == "portrait.jpg"
    assert p["mime_type"] == "image/jpeg"
    assert p["width"] == 640 and p["height"] == 480
    assert p["file_size"] == len(jpeg)
    assert p["quality_status"] == QualityStatus.UNSUITABLE.value
    assert p["approved"] is False
    assert p["thumbnail_url"].endswith(f"/photos/{p['id']}/thumbnail")

    # No internal filesystem information may leak.
    assert "storage_path" not in p and "stored_filename" not in p
    assert "storage_path" not in result and "stored_filename" not in result

    # File exists under the private data root only.
    stored = settings.data_dir / "people" / person["id"] / "original"
    assert stored.exists() and any(stored.iterdir())


@requires_model
def test_upload_valid_png_and_webp(client, person):
    resp = _upload(
        client,
        person["id"],
        [("a.png", _png_bytes(), "image/png"), ("b.webp", _webp_bytes(), "image/webp")],
    )
    assert resp.status_code == 201, resp.text
    results = resp.json()["results"]
    assert all(r["photo_id"] is not None for r in results)
    by_name = {r["original_filename"]: r for r in results}
    # Solid-color fixtures → analyzed as no-face.
    assert by_name["a.png"]["quality_status"] == QualityStatus.UNSUITABLE.value
    assert by_name["b.webp"]["quality_status"] == QualityStatus.UNSUITABLE.value

    photos = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    mimes = {p["original_filename"]: p["mime_type"] for p in photos}
    assert mimes["a.png"] == "image/png"
    assert mimes["b.webp"] == "image/webp"


# ---------------------------------------------------------------- failures


def test_upload_corrupt_jpeg_gets_decode_failure(client, person):
    resp = _upload(client, person["id"], [("broken.jpg", _corrupt_jpeg(), "image/jpeg")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is None
    assert result["rejection_reason"] == "MEDIA_DECODE_FAILURE"
    assert client.get(f"/api/people/{person['id']}/photos").json()["photos"] == []


def test_upload_text_file_named_jpg_rejected_as_unsupported(client, person):
    resp = _upload(client, person["id"], [("fake.jpg", _fake_jpg_text(), "image/jpeg")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is None
    assert result["rejection_reason"] == "UNSUPPORTED_FORMAT"


def test_upload_heic_rejected_unsupported(client, person):
    resp = _upload(client, person["id"], [("shot.heic", _heic_magic(), "image/heic")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is None
    assert result["rejection_reason"] == "UNSUPPORTED_FORMAT"
    # Normalization is deferred — the note must not claim silent conversion.
    assert "convert to JPEG/PNG/WEBP" in result["measurements"].get("note", "")


@requires_model
def test_upload_unsupported_extension_with_image_magic_accepted(client, person):
    # Extension is never trusted; a valid JPEG named .txt is still a valid image.
    resp = _upload(client, person["id"], [("photo.txt", _jpeg_bytes(), "application/octet-stream")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is not None
    assert result["rejection_reason"] == "NO_FACE"  # accepted, then analyzed


# ---------------------------------------------------------------- format allowlist


def test_upload_gif_bmp_tiff_rejected_not_in_allowlist(client, person):
    # Valid, Pillow-decodable images outside the application allowlist (JPEG/PNG/WEBP)
    # must be rejected with an explicit reason — never accepted just because they decode.
    resp = _upload(
        client,
        person["id"],
        [
            ("a.gif", _gif_bytes(), "image/gif"),
            ("b.bmp", _bmp_bytes(), "image/bmp"),
            ("c.tiff", _tiff_bytes(), "image/tiff"),
        ],
    )
    assert resp.status_code == 201, resp.text
    results = resp.json()["results"]
    assert len(results) == 3
    for r in results:
        assert r["photo_id"] is None
        assert r["rejection_reason"] == "UNSUPPORTED_FORMAT"
    assert {r["measurements"].get("detected_format") for r in results} == {"GIF", "BMP", "TIFF"}
    assert client.get(f"/api/people/{person['id']}/photos").json()["photos"] == []


def test_extension_spoofing_cannot_bypass_allowlist(client, person):
    # The allowlist is content-based: a valid TIFF renamed .jpg is still rejected…
    resp = _upload(client, person["id"], [("tiff.jpg", _tiff_bytes(), "image/jpeg")])
    result = resp.json()["results"][0]
    assert result["photo_id"] is None
    assert result["rejection_reason"] == "UNSUPPORTED_FORMAT"
    assert result["measurements"].get("detected_format") == "TIFF"

    # …a valid GIF renamed .png is rejected too…
    resp = _upload(client, person["id"], [("gif.png", _gif_bytes(), "image/png")])
    result = resp.json()["results"][0]
    assert result["photo_id"] is None
    assert result["rejection_reason"] == "UNSUPPORTED_FORMAT"
    assert result["measurements"].get("detected_format") == "GIF"

    # …and a valid JPEG named .txt is accepted (content wins over extension).
    resp = _upload(client, person["id"], [("photo.txt", _jpeg_bytes(), "application/octet-stream")])
    assert resp.json()["results"][0]["photo_id"] is not None

    # Nothing outside the allowlist was stored.
    photos = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    assert [p["original_filename"] for p in photos] == ["photo.txt"]


def test_upload_oversized_file_rejected(client, person, monkeypatch):
    # Shrink the limit for this test so we don't allocate 20 MB.
    monkeypatch.setattr("app.config.MAX_UPLOAD_BYTES", 1024)
    resp = _upload(client, person["id"], [("big.jpg", _jpeg_bytes(), "image/jpeg")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is None
    assert result["rejection_reason"] == "FILE_TOO_LARGE"


def test_upload_mixed_batch_partial_results(client, person):
    resp = _upload(
        client,
        person["id"],
        [
            ("good.jpg", _jpeg_bytes(), "image/jpeg"),
            ("bad.txt", _fake_jpg_text(), "text/plain"),
            ("broken.jpg", _corrupt_jpeg(), "image/jpeg"),
        ],
    )
    assert resp.status_code == 201, resp.text
    results = resp.json()["results"]
    assert len(results) == 3
    good = [r for r in results if r["original_filename"] == "good.jpg"][0]
    bad_txt = [r for r in results if r["original_filename"] == "bad.txt"][0]
    broken = [r for r in results if r["original_filename"] == "broken.jpg"][0]
    assert good["photo_id"] is not None
    assert bad_txt["photo_id"] is None and bad_txt["rejection_reason"] == "UNSUPPORTED_FORMAT"
    assert broken["photo_id"] is None and broken["rejection_reason"] == "MEDIA_DECODE_FAILURE"

    # Only the good file is stored/listed.
    photos = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    assert [p["original_filename"] for p in photos] == ["good.jpg"]


# ---------------------------------------------------------------- filenames


def test_path_traversal_filename_is_safe(client, person):
    resp = _upload(client, person["id"], [("../../../../evil.jpg", _jpeg_bytes(), "image/jpeg")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is not None
    assert result["original_filename"] == "../../../../evil.jpg"  # metadata only


def test_weird_unicode_filename_accepted(client, person):
    name = "portr\u00e4it \u2764\ufe0f \u65e5\u672c\u8a9e.jpg"
    resp = _upload(client, person["id"], [(name, _jpeg_bytes(), "image/jpeg")])
    assert resp.status_code == 201, resp.text
    result = resp.json()["results"][0]
    assert result["photo_id"] is not None
    assert result["original_filename"] == name


def test_duplicate_filenames_both_stored(client, person):
    resp = _upload(
        client,
        person["id"],
        [("same.jpg", _jpeg_bytes(), "image/jpeg"), ("same.jpg", _png_bytes(), "image/png")],
    )
    assert resp.status_code == 201, resp.text
    ids = {r["photo_id"] for r in resp.json()["results"]}
    assert len(ids) == 2 and None not in ids
    photos = client.get(f"/api/people/{person['id']}/photos").json()["photos"]
    assert len(photos) == 2


# ---------------------------------------------------------------- ownership / access


def test_photos_scoped_to_person(client, person):
    other = client.post("/api/people", json={"display_name": "Other", "relationship": "Friend"}).json()
    _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")])
    assert client.get(f"/api/people/{other['id']}/photos").json()["photos"] == []


def test_cross_person_access_blocked(client, person):
    other = client.post("/api/people", json={"display_name": "Other", "relationship": "Friend"}).json()
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]

    assert client.get(f"/api/people/{other['id']}/photos/{photo_id}").status_code == 404
    assert client.get(f"/api/people/{other['id']}/photos/{photo_id}/file").status_code == 404
    assert client.get(f"/api/people/{other['id']}/photos/{photo_id}/thumbnail").status_code == 404
    assert client.delete(f"/api/people/{other['id']}/photos/{photo_id}").status_code == 404

    # The photo is untouched.
    assert client.get(f"/api/people/{person['id']}/photos").json()["photos"][0]["id"] == photo_id


def test_photo_on_unknown_person_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/people/{pid}/photos").status_code == 404
    assert client.post(f"/api/people/{pid}/photos", files=[("files", ("a.jpg", _jpeg_bytes(), "image/jpeg"))]).status_code == 404


# ---------------------------------------------------------------- preview / file


def test_file_serves_original_bytes(client, person):
    jpeg = _jpeg_bytes()
    photo_id = _upload(client, person["id"], [("a.jpg", jpeg, "image/jpeg")]).json()["results"][0]["photo_id"]
    resp = client.get(f"/api/people/{person['id']}/photos/{photo_id}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == jpeg  # byte-for-byte untouched (FR-011)


def test_file_kind_normalized_not_produced(client, person):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    resp = client.get(f"/api/people/{person['id']}/photos/{photo_id}/file", params={"kind": "normalized"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PHOTO_NOT_FOUND"


def test_file_invalid_kind_400(client, person):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    resp = client.get(f"/api/people/{person['id']}/photos/{photo_id}/file", params={"kind": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_thumbnail_served_small(client, person):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(1600, 1200), "image/jpeg")]).json()["results"][0]["photo_id"]
    resp = client.get(f"/api/people/{person['id']}/photos/{photo_id}/thumbnail")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(resp.content)) as thumb:
        assert max(thumb.size) <= 300


# ---------------------------------------------------------------- delete


def test_delete_photo_removes_row_and_files(client, person, settings):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    person_dir = settings.data_dir / "people" / person["id"]
    original_files = list((person_dir / "original").iterdir())
    assert len(original_files) == 1
    thumb_files = list((person_dir / "thumbs").iterdir())
    assert len(thumb_files) == 1

    resp = client.delete(f"/api/people/{person['id']}/photos/{photo_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/people/{person['id']}/photos").json()["photos"] == []
    assert not (person_dir / "original").exists() or list((person_dir / "original").iterdir()) == []
    assert not (person_dir / "thumbs").exists() or list((person_dir / "thumbs").iterdir()) == []


def test_delete_photo_missing_file_still_succeeds(client, person, settings):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    # Simulate a vanished backing file.
    for f in (settings.data_dir / "people" / person["id"] / "original").iterdir():
        f.unlink()
    resp = client.delete(f"/api/people/{person['id']}/photos/{photo_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/people/{person['id']}/photos").json()["photos"] == []


def test_delete_unknown_photo_404(client, person):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.delete(f"/api/people/{person['id']}/photos/{pid}").status_code == 404


def test_file_endpoint_missing_backing_file_404(client, person, settings):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    for f in (settings.data_dir / "people" / person["id"] / "original").iterdir():
        f.unlink()
    resp = client.get(f"/api/people/{person['id']}/photos/{photo_id}/file")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PHOTO_NOT_FOUND"


# ---------------------------------------------------------------- person delete


def test_person_delete_removes_photo_files(client, person, settings):
    _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")])
    assert (settings.data_dir / "people" / person["id"]).exists()
    resp = client.delete(f"/api/people/{person['id']}")
    assert resp.status_code == 204
    assert not (settings.data_dir / "people" / person["id"]).exists()


# ---------------------------------------------------------------- audit


@requires_model
def test_photo_upload_and_delete_audited(client, person):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    client.delete(f"/api/people/{person['id']}/photos/{photo_id}")

    entries = client.get("/api/audit").json()["entries"]
    actions = [e["action"] for e in entries]
    assert AuditAction.PHOTO_UPLOADED.value in actions
    assert AuditAction.PHOTO_DELETED.value in actions

    upload = next(e for e in entries if e["action"] == AuditAction.PHOTO_UPLOADED.value)
    assert upload["entity_type"] == "photo"
    assert upload["entity_id"] == photo_id
    # Audit metadata only — no image bytes, no secrets, no absolute paths.
    details = upload["details"] or {}
    assert set(details) == {"person_id", "mime_type", "width", "height", "file_size", "quality_status"}
    assert all(isinstance(v, (str, int, bool)) or v is None for v in details.values())


# ---------------------------------------------------------------- malformed input


def test_malformed_person_uuid_400(client):
    resp = client.get("/api/people/not-a-uuid/photos")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_malformed_photo_uuid_400(client, person):
    resp = client.get(f"/api/people/{person['id']}/photos/not-a-uuid")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- privacy invariants


@requires_model
def test_no_image_bytes_in_database(app, client, person):
    photo_id = _upload(client, person["id"], [("a.jpg", _jpeg_bytes(), "image/jpeg")]).json()["results"][0]["photo_id"]
    with app.state.session_factory() as session:
        from app.models.photo import EnrollmentPhoto

        row = session.get(EnrollmentPhoto, photo_id)
        assert row is not None
        # The row stores metadata + a relative storage path, never image bytes.
        assert row.storage_path.startswith(f"people/{person['id']}/original/")
        assert row.file_size > 0
        assert row.face_count == 0  # Phase 4 analysis ran (solid color, no face)
        assert row.quality_status == QualityStatus.UNSUITABLE.value
        assert row.approved is False
        assert row.enrolled_in_frigate is False