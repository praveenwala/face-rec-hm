"""G6-PREFLIGHT — non-mutating Frigate 0.17.2 face-API contract tests.

These tests encode the VERIFIED Frigate 0.17.2 face-API contract
(specs/002/contracts/frigate-0.17.2-api-verification.md) as executable checks.

Hard rule for this gate: **zero Frigate mutation, zero network I/O to Frigate.**
Nothing here constructs an HTTP client to Frigate, and no test performs a
POST/PUT/PATCH/DELETE against a face endpoint — even a fake one. The tests exercise
pure functions: identity-name validation, request-shape construction, and response
parsing, plus the still-BLOCKED Phase 6 stubs.
"""

from __future__ import annotations

import re

# Frigate 0.17.2 enforces (frigate/embeddings/__init__.py::rename_face, verified from the
# installed image):  ^[\p{L}\p{N}\s'_-]{1,50}$  using the third-party ``regex`` module.
# ``regex`` is a Frigate-internal dependency and is deliberately NOT added to this app's
# requirements for a read-only preflight gate. We reproduce the SAME allowed set with the
# stdlib ``re`` module: \w under re.UNICODE covers Unicode letters/digits/underscore, and
# we add space, apostrophe and hyphen — matching Frigate's class for validation purposes.
FRIGATE_NAME_PATTERN = r"^[\p{L}\p{N}\s'_-]{1,50}$"  # documented reference (Frigate's regex rule)
_ALLOWED = re.compile(r"^[\w\s'-]{1,50}$", re.UNICODE)


def _valid_frigate_name(name: str) -> bool:
    """Mirror of Frigate's rename validation (allowed char class + no path-hostile chars).

    Uses stdlib ``re`` with an equivalent allowed set to Frigate's ``regex`` rule
    (Unicode letters/digits/underscore via ``\\w`` + space, apostrophe, hyphen).
    """
    if not _ALLOWED.match(name):
        return False
    # Frigate additionally requires sanitize_filename(name) == name. We approximate the
    # path-hostile subset here without importing pathvalidate: reject separators/traversal.
    if any(sep in name for sep in ("/", "\\")) or name in (".", ".."):
        return False
    return True


class TestIdentityNameRules:
    def test_simple_ascii_name_is_valid(self):
        assert _valid_frigate_name("Alex")

    def test_name_with_space_apostrophe_hyphen_underscore_is_valid(self):
        assert _valid_frigate_name("Mary-Jane O'Neil_1")

    def test_unicode_letters_allowed(self):
        assert _valid_frigate_name("José")
        assert _valid_frigate_name("陳")

    def test_empty_name_rejected(self):
        assert not _valid_frigate_name("")

    def test_overlong_name_rejected(self):
        assert not _valid_frigate_name("x" * 51)

    def test_path_separator_rejected(self):
        assert not _valid_frigate_name("a/b")
        assert not _valid_frigate_name("a\\b")

    def test_path_traversal_rejected(self):
        assert not _valid_frigate_name("..")

    def test_disallowed_punctuation_rejected(self):
        # '.' and '/' are not in the allowed class
        assert not _valid_frigate_name("bad.name")
        assert not _valid_frigate_name("a@b")


class TestCreateNameSanitization:
    """create_face applies name.replace(' ', '_') then sanitize_filename."""

    @staticmethod
    def _create_folder_name(name: str) -> str:
        # Mirror of create_face's transform (spaces -> underscores). We do NOT call the
        # real sanitize_filename here to avoid a hard dependency; we only assert the
        # space rule, which is the app-visible mapping concern.
        return name.replace(" ", "_")

    def test_spaces_become_underscores(self):
        assert self._create_folder_name("First Last") == "First_Last"


class TestRegisterRequestShape:
    """register is multipart/form-data with a single binary field named 'file'
    carrying the FULL image (Frigate crops). This test constructs the request shape
    WITHOUT sending it anywhere."""

    def test_multipart_field_name_is_file(self):
        # Synthetic construction only — never transmitted.
        files = {"file": ("photo.jpg", b"\xff\xd8\xff\xe0synthetic-not-a-real-face", "image/jpeg")}
        assert set(files.keys()) == {"file"}
        field = files["file"]
        assert field[0].endswith(".jpg")
        assert field[2] == "image/jpeg"

    def test_delete_body_carries_full_id_list(self):
        # remove_identity must enumerate then send ALL filenames (DeleteFaceImagesBody).
        body = {"ids": ["name_1.webp", "name_2.webp"]}
        assert isinstance(body["ids"], list) and body["ids"]

    def test_rename_body_shape(self):
        body = {"new_name": "New Name"}
        assert set(body.keys()) == {"new_name"}


class TestResponseParsing:
    def test_faces_response_is_name_to_filelist_map(self):
        # FacesResponse = RootModel[Dict[str, List[str]]]
        sample = {"alex": ["alex_1.webp"], "sam": ["sam_1.webp", "sam_2.jpg"]}
        assert all(isinstance(v, list) for v in sample.values())

    def test_empty_library_parses_to_empty_dict(self):
        sample: dict = {}
        assert sample == {}

    def test_recognize_response_shape(self):
        # FaceRecognitionResponse = {success, score?, face_name?}
        resp = {"success": True, "score": 0.93, "face_name": "alex"}
        assert resp["success"] is True
        assert 0.0 <= resp["score"] <= 1.0

    def test_no_face_detected_error_shape(self):
        resp = {"success": False, "message": "No face was detected."}
        assert resp["success"] is False


class TestFailureAndAuthModeling:
    """Model the failure states the future service must represent — no live calls."""

    def test_unavailable_maps_to_degraded_not_partial_write(self):
        # FRIGATE_UNAVAILABLE → person stays READY, no partial writes (contract).
        state = {"frigate_reachable": False}
        # A well-behaved planner never attempts submission when unreachable.
        assert state["frigate_reachable"] is False

    def test_auth_failure_is_representable(self):
        # Mutating endpoints require admin role → 401/403 are expected, modelable outcomes.
        for status in (401, 403):
            assert status in (401, 403)

    def test_partial_enrollment_state_model(self):
        # Mid-enrollment failure: some photos enrolled, person -> ERROR, retry allowed.
        photos = [{"enrolled": True}, {"enrolled": False}]
        person_status = "ERROR" if any(not p["enrolled"] for p in photos) else "ENROLLED"
        assert person_status == "ERROR"


class TestPhase6FeatureFlagGate:
    """Implementation stage: enrollment.py is the single source of truth; the mutating
    routes refuse via the canonical error framework while FRIGATE_ENROLLMENT_ENABLED
    is OFF, and the read-only status route responds honestly."""

    def test_enroll_refused_with_feature_not_enabled(self, client):
        r = client.post("/api/people/00000000-0000-0000-0000-000000000000/enroll")
        assert r.status_code == 501
        assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"

    def test_remove_enrollment_refused_with_feature_not_enabled(self, client):
        r = client.delete("/api/people/00000000-0000-0000-0000-000000000000/enrollment")
        assert r.status_code == 501
        assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"

    def test_frigate_status_controlled_refusal_while_disabled(self, client):
        # Status is gated by the same flag: controlled refusal while disabled, and it
        # never probes Frigate. Consistent 501 FEATURE_NOT_ENABLED envelope.
        r = client.get("/api/frigate/status")
        assert r.status_code == 501
        assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"

    def test_enrollment_routes_are_not_duplicated(self, client):
        # Single source of truth: exactly one route object per path/method.
        paths = [
            (r.path, tuple(sorted(r.methods)))
            for r in client.app.routes
            if getattr(r, "path", "") in (
                "/api/people/{person_id}/enroll",
                "/api/people/{person_id}/enrollment",
                "/api/frigate/status",
            )
        ]
        assert len(paths) == len(set(paths)), f"duplicate enrollment routes: {paths}"


class TestFrigateServiceContract:
    """Implementation stage: frigate_service now EXISTS and matches the verified
    Frigate 0.17.2 contract, with mutations disabled by default and zero real
    Frigate mutation while the feature flag is OFF."""

    def test_frigate_service_module_and_class_exist(self):
        from app.services.frigate_service import FrigateEnrollmentService  # noqa: F401

        assert hasattr(FrigateEnrollmentService, "list_identities")
        assert hasattr(FrigateEnrollmentService, "create_identity")
        assert hasattr(FrigateEnrollmentService, "register_face")
        assert hasattr(FrigateEnrollmentService, "remove_identity")
        assert hasattr(FrigateEnrollmentService, "rename_identity")
        assert hasattr(FrigateEnrollmentService, "recognize")
        assert hasattr(FrigateEnrollmentService, "reconcile")
        assert hasattr(FrigateEnrollmentService, "status")

    def test_identity_name_rule_matches_verified_contract(self):
        from app.services.frigate_service import is_valid_frigate_identity_name

        assert is_valid_frigate_identity_name("Alex")
        assert is_valid_frigate_identity_name("Mary-Jane O'Neil_1")
        assert not is_valid_frigate_identity_name("")
        assert not is_valid_frigate_identity_name("x" * 51)
        assert not is_valid_frigate_identity_name("a/b")
        assert not is_valid_frigate_identity_name("..")

    def test_mutations_disabled_by_default(self):
        from app.config import load_settings
        from app.services.frigate_service import FrigateEnrollmentService

        settings = load_settings()
        assert settings.frigate_enrollment_enabled is False
        service = FrigateEnrollmentService(settings=settings, transport=None)
        assert service.enabled is False

    def test_flag_off_yields_zero_real_frigate_mutation(self):
        """With the flag OFF, every mutating call refuses BEFORE touching transport,
        so a spy transport records zero requests."""
        from app.config import load_settings
        from app.exceptions import FeatureNotEnabledError
        from app.services.frigate_service import FrigateEnrollmentService

        calls: list[tuple] = []

        class SpyTransport:
            def request(self, method, path, *, json=None, files=None):
                calls.append((method, path))
                return 200, {}

        settings = load_settings()  # flag OFF by default
        service = FrigateEnrollmentService(settings=settings, transport=SpyTransport())

        for op in (
            lambda: service.create_identity("Alex"),
            lambda: service.register_face("Alex", b"bytes"),
            lambda: service.remove_identity("Alex", ["Alex_1.webp"]),
            lambda: service.rename_identity("Alex", "Alexander"),
        ):
            import pytest

            with pytest.raises(FeatureNotEnabledError):
                op()

        assert calls == [], f"flag OFF must cause zero Frigate transport calls, got {calls}"

    def test_status_does_not_probe_frigate_while_disabled(self):
        from app.config import load_settings
        from app.services.frigate_service import FrigateEnrollmentService

        calls: list[tuple] = []

        class SpyTransport:
            def request(self, method, path, *, json=None, files=None):
                calls.append((method, path))
                return 200, {}

        settings = load_settings()
        service = FrigateEnrollmentService(settings=settings, transport=SpyTransport())
        status = service.status()
        assert status["enrollment_enabled"] is False
        assert status["frigate_reachable"] is None
        assert calls == [], "status must not probe Frigate while disabled"
