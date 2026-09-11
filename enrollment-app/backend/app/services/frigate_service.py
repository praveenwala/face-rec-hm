"""FrigateEnrollmentService — the single boundary to Frigate's face API (Phase 6).

Raw Frigate HTTP calls must never appear in controllers/routers/UI (spec FR-028);
they live only here. The surface matches the VERIFIED Frigate 0.17.2 contract
(specs/002/contracts/frigate-0.17.2-api-verification.md):

    GET    /api/faces                      list registered identities
    POST   /api/faces/{name}/create        create identity folder        (admin)
    POST   /api/faces/{name}/register      register a face image (full)  (admin)
    POST   /api/faces/{name}/delete        delete face images            (admin)
    PUT    /api/faces/{old}/rename         rename identity               (admin)
    POST   /api/faces/recognize            non-persisting verify

HARD SAFETY INVARIANT (feature flag):
    While ``settings.frigate_enrollment_enabled`` is False, this service performs
    ZERO mutating Frigate requests. Every mutating method refuses up-front with
    ``FeatureNotEnabledError`` BEFORE any network/transport call. Read-only status
    is still allowed (and itself degrades safely when the flag is off).

Transport is injected: production wires a real HTTP transport; tests wire a fake
whose responses match the 0.17.2 contract. No real Frigate mutation occurs in tests.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Protocol

from app.config import Settings
from app.exceptions import (
    FeatureNotEnabledError,
    FrigateAuthError,
    FrigateEnrollmentError,
    FrigateUnavailableError,
    IdentityConflictError,
)

_LOG = logging.getLogger(__name__)

# Verified Frigate 0.17.2 identity-name rule (frigate/embeddings/__init__.py::rename_face):
#   ^[\p{L}\p{N}\s'_-]{1,50}$  (Unicode letters/digits, space, apostrophe, underscore, hyphen)
# Reproduced with stdlib re: \w (UNICODE) covers letters/digits/underscore.
_ALLOWED_NAME_RE = re.compile(r"^[\w\s'-]{1,50}$", re.UNICODE)


def _sanitize_create_name(name: str) -> str:
    """Mirror Frigate ``create_face``: spaces -> underscore, strip path-hostile chars.

    Deterministic and offline — used to derive a *candidate* frigate_identity_name
    without ever contacting Frigate.
    """
    candidate = name.strip().replace(" ", "_")
    # Drop anything outside the allowed class; collapse repeats of separators.
    candidate = "".join(ch for ch in candidate if _ALLOWED_NAME_RE.match(ch) or ch in "_-")
    candidate = candidate.strip("_-") or "person"
    return candidate[:50].strip("_-") or "person"


def is_valid_frigate_identity_name(name: str) -> bool:
    """True iff ``name`` satisfies Frigate's identity-name rule and has no path chars."""
    if not _ALLOWED_NAME_RE.match(name or ""):
        return False
    if "/" in name or "\\" in name or name in (".", ".."):
        return False
    return True


class FrigateTransport(Protocol):
    """Minimal HTTP-ish transport. Returns (status_code, json_body).

    ``files`` present => multipart upload (register/recognize). Implementations must
    raise ``ConnectionError``/``TimeoutError`` for unreachable Frigate so the service
    can map them to ``FrigateUnavailableError``.
    """

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = ...,
        files: dict | None = ...,
    ) -> tuple[int, Any]:
        ...


class FrigateEnrollmentService:
    """The only place that talks to Frigate's face API.

    ``transport`` is optional: when the enrollment flag is OFF no transport is needed
    for the read-only status path, and mutating methods refuse before using it.
    """

    def __init__(
        self,
        settings: Settings,
        transport: FrigateTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    # ---- feature-flag guard ----------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._settings.frigate_enrollment_enabled

    def _require_enabled(self, operation: str) -> None:
        """Controlled refusal: refuse BEFORE any transport call while the flag is OFF."""
        if not self.enabled:
            raise FeatureNotEnabledError(
                f"Frigate enrollment is disabled (FRIGATE_ENROLLMENT_ENABLED=false); "
                f"'{operation}' performs no Frigate mutation.",
            )

    def _require_transport(self, operation: str) -> FrigateTransport:
        if self._transport is None:
            # Flag ON but no transport wired => unavailable, never a silent no-op.
            raise FrigateUnavailableError(
                f"No Frigate transport configured for '{operation}'.",
            )
        return self._transport

    def _call(self, method: str, path: str, **kw: Any) -> tuple[int, Any]:
        transport = self._require_transport(f"{method} {path}")
        try:
            return transport.request(method, path, **kw)
        except (ConnectionError, TimeoutError) as exc:
            raise FrigateUnavailableError(f"Frigate unreachable: {exc}") from exc

    @staticmethod
    def _raise_for_status(status: int, body: Any, *, operation: str) -> Any:
        if status in (401, 403):
            raise FrigateAuthError(f"Frigate auth failed for '{operation}' (HTTP {status}).")
        if status == 503 or status == 502:
            raise FrigateUnavailableError(f"Frigate unavailable for '{operation}' (HTTP {status}).")
        if status >= 400:
            msg = body.get("message") if isinstance(body, dict) else str(body)
            raise FrigateEnrollmentError(f"Frigate '{operation}' failed (HTTP {status}): {msg}")
        return body

    # ---- read-only -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Read-only status. Never mutates. Safe whether or not the flag is on.

        When the flag is off (or no transport), reports enrollment disabled and does
        not probe Frigate — honest degraded state, never a fake success.
        """
        if not self.enabled or self._transport is None:
            return {
                "enrollment_enabled": self.enabled,
                "frigate_reachable": None,  # not probed (constitution IV.3: unavailable != false)
                "api_url": self._settings.frigate_api_url,
                "identities": None,
            }
        try:
            identities = self.list_identities()
            return {
                "enrollment_enabled": True,
                "frigate_reachable": True,
                "api_url": self._settings.frigate_api_url,
                "identities": sorted(identities.keys()),
            }
        except FrigateUnavailableError:
            return {
                "enrollment_enabled": True,
                "frigate_reachable": False,
                "api_url": self._settings.frigate_api_url,
                "identities": None,
            }

    def list_identities(self) -> dict[str, list[str]]:
        """GET /api/faces -> {name: [filenames]}. Read-only (no flag required)."""
        status, body = self._call("GET", "/api/faces")
        body = self._raise_for_status(status, body, operation="list_identities")
        return body if isinstance(body, dict) else {}

    def recognize(self, image_bytes: bytes) -> dict[str, Any]:
        """POST /api/faces/recognize — non-persisting verification. Read-only."""
        status, body = self._call(
            "POST", "/api/faces/recognize", files={"file": ("probe.jpg", image_bytes, "image/jpeg")}
        )
        return self._raise_for_status(status, body, operation="recognize")

    # ---- mutating (all gated by the feature flag) ------------------------------

    def create_identity(self, name: str) -> dict[str, Any]:
        self._require_enabled("create_identity")
        if not is_valid_frigate_identity_name(name):
            raise IdentityConflictError(f"Invalid Frigate identity name: {name!r}")
        status, body = self._call("POST", f"/api/faces/{name}/create")
        return self._raise_for_status(status, body, operation="create_identity")

    def register_face(self, name: str, image_bytes: bytes, *, filename: str = "photo.jpg") -> dict[str, Any]:
        """POST /api/faces/{name}/register with the FULL image (Frigate crops)."""
        self._require_enabled("register_face")
        if not is_valid_frigate_identity_name(name):
            raise IdentityConflictError(f"Invalid Frigate identity name: {name!r}")
        status, body = self._call(
            "POST",
            f"/api/faces/{name}/register",
            files={"file": (filename, image_bytes, "image/jpeg")},
        )
        body = self._raise_for_status(status, body, operation="register_face")
        # Frigate returns {"success": false, "message": "No face was detected."} at 200/400.
        if isinstance(body, dict) and body.get("success") is False:
            raise FrigateEnrollmentError(
                f"Frigate rejected the image for '{name}': {body.get('message')}"
            )
        return body

    def remove_identity(self, name: str, image_ids: list[str] | None = None) -> dict[str, Any]:
        """POST /api/faces/{name}/delete with the full id list (enumerate first)."""
        self._require_enabled("remove_identity")
        ids = image_ids
        if ids is None:
            identities = self.list_identities()
            ids = list(identities.get(name, []))
        status, body = self._call("POST", f"/api/faces/{name}/delete", json={"ids": ids})
        return self._raise_for_status(status, body, operation="remove_identity")

    def rename_identity(self, old_name: str, new_name: str) -> dict[str, Any]:
        self._require_enabled("rename_identity")
        if not is_valid_frigate_identity_name(new_name):
            raise IdentityConflictError(f"Invalid Frigate identity name: {new_name!r}")
        status, body = self._call(
            "PUT", f"/api/faces/{old_name}/rename", json={"new_name": new_name}
        )
        return self._raise_for_status(status, body, operation="rename_identity")

    # ---- reconciliation (read-only diff, never auto-mutates) -------------------

    def reconcile(self, local_identity_names: list[str]) -> dict[str, list[str]]:
        """Compare local frigate_identity_names vs GET /api/faces. Never mutates."""
        remote = set(self.list_identities().keys()) if self._transport is not None else set()
        local = set(local_identity_names)
        return {
            "only_local": sorted(local - remote),
            "only_frigate": sorted(remote - local),
            "in_both": sorted(local & remote),
        }
