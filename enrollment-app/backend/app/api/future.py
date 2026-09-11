"""Reserved router for genuinely future/unimplemented endpoints.

The Phase 6 enrollment routes (POST /api/people/{id}/enroll,
DELETE /api/people/{id}/enrollment, GET /api/frigate/status) are NO LONGER here —
they now live in ``app/api/enrollment.py`` as the single source of truth, gated by
the FRIGATE_ENROLLMENT_ENABLED feature flag. Do not re-add enrollment stubs here;
duplicate routes are prohibited.

This router is intentionally empty today. Add future non-enrollment stubs here if and
when they are needed.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["future"])
