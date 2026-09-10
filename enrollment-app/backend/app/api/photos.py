"""Photo endpoints (Phase 3, contracts/rest-api.md).

POST   /api/people/{id}/photos                       — multi-file upload (per-file results)
GET    /api/people/{id}/photos                       — metadata list (no bytes, no paths)
GET    /api/people/{id}/photos/{photo_id}            — metadata detail
GET    /api/people/{id}/photos/{photo_id}/file?kind=original|normalized — image bytes
GET    /api/people/{id}/photos/{photo_id}/thumbnail  — small preview (max ~300px)
DELETE /api/people/{id}/photos/{photo_id}            — 204; row + original/normalized/approved + thumb

Phase 3 boundary: ingestion only — no face detection, no quality classification
(beyond PENDING), no approval, no enrollment. `kind=normalized` is not produced
until Phase 4 and returns an explicit 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings, parse_uuid
from app.config import Settings
from app.exceptions import PhotoNotFoundError, ValidationAppError
from app.models.enums import ErrorCode
from app.services.photo_service import PhotoService

router = APIRouter(prefix="/api/people", tags=["photos"])


def _service(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> PhotoService:
    return PhotoService(session, settings)


@router.post("/{person_id}/photos", status_code=201)
async def upload_photos(
    person_id: str,
    files: list[UploadFile] = File(...),
    service: PhotoService = Depends(_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    pid = parse_uuid(person_id, name="person id")
    if not files:
        raise ValidationAppError(
            "No files were provided", code=ErrorCode.VALIDATION_ERROR
        )
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        payloads.append((f.filename or "upload", data))
    return {"results": service.upload_files(pid, payloads)}


@router.get("/{person_id}/photos")
def list_photos(person_id: str, service: PhotoService = Depends(_service)) -> dict:
    return {"photos": service.list_photos(parse_uuid(person_id, name="person id"))}


@router.get("/{person_id}/photos/{photo_id}")
def get_photo(
    person_id: str, photo_id: str, service: PhotoService = Depends(_service)
) -> dict:
    return service.get_photo(
        parse_uuid(person_id, name="person id"),
        parse_uuid(photo_id, name="photo id"),
    )


@router.get("/{person_id}/photos/{photo_id}/file")
def photo_file(
    person_id: str,
    photo_id: str,
    kind: str = "original",
    service: PhotoService = Depends(_service),
) -> Response:
    pid = parse_uuid(person_id, name="person id")
    phid = parse_uuid(photo_id, name="photo id")
    if kind not in ("original", "normalized"):
        raise ValidationAppError(
            f"kind must be 'original' or 'normalized', got {kind!r}",
            code=ErrorCode.VALIDATION_ERROR,
        )
    if kind == "normalized":
        # Not produced until Phase 4 (HEIC→JPEG etc.). Honest 404, never a fallback.
        raise PhotoNotFoundError(
            "normalized copy is not produced in this phase (Phase 4)",
            details={"kind": "normalized", "photo_id": phid},
        )
    data, mime = service.get_original_bytes(pid, phid)
    return Response(content=data, media_type=mime)


@router.get("/{person_id}/photos/{photo_id}/thumbnail")
def photo_thumbnail(
    person_id: str, photo_id: str, service: PhotoService = Depends(_service)
) -> Response:
    data, mime = service.get_thumbnail_bytes(
        parse_uuid(person_id, name="person id"),
        parse_uuid(photo_id, name="photo id"),
    )
    return Response(content=data, media_type=mime)


@router.delete("/{person_id}/photos/{photo_id}", status_code=204)
def delete_photo(
    person_id: str, photo_id: str, service: PhotoService = Depends(_service)
) -> Response:
    service.delete_photo(
        parse_uuid(person_id, name="person id"),
        parse_uuid(photo_id, name="photo id"),
    )
    return Response(status_code=204)