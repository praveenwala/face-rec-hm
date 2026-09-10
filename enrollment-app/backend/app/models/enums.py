"""Canonical enums shared across models, services, and the API.

Values are stable strings — the API and DB store exactly these literals
(data-model.md, contracts/photo-quality.md, contracts/rest-api.md).
"""

from __future__ import annotations

from enum import Enum


class Relationship(str, Enum):
    FAMILY = "Family"
    FRIEND = "Friend"
    NEIGHBOR = "Neighbor"
    OTHER_KNOWN = "Other Known"


class EnrollmentStatus(str, Enum):
    DRAFT = "DRAFT"          # person created, no photos yet
    NOT_READY = "NOT_READY"  # fewer than 5 suitable AND approved photos
    READY = "READY"          # >= 5 suitable AND approved photos
    ENROLLING = "ENROLLING"  # enrollment in progress (Phase 6 only)
    ENROLLED = "ENROLLED"    # enrolled in Frigate (Phase 6 only)
    ERROR = "ERROR"          # last enrollment attempt failed (Phase 6 only)


class QualityStatus(str, Enum):
    PENDING = "PENDING"                  # processing in progress
    SUITABLE = "SUITABLE"                # passed all checks (once explicitly approved)
    UNSUITABLE = "UNSUITABLE"            # failed a blocking check
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # needs human review (multi-face, near-dup)


class RejectionReason(str, Enum):
    MEDIA_DECODE_FAILURE = "MEDIA_DECODE_FAILURE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    NO_FACE = "NO_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    FACE_TOO_SMALL = "FACE_TOO_SMALL"
    TOO_BLURRY = "TOO_BLURRY"
    UNDEREXPOSED = "UNDEREXPOSED"
    OVEREXPOSED = "OVEREXPOSED"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"


class AuditAction(str, Enum):
    PERSON_CREATED = "PERSON_CREATED"
    PERSON_UPDATED = "PERSON_UPDATED"
    RELATIONSHIP_CHANGED = "RELATIONSHIP_CHANGED"
    PERSON_DISABLED = "PERSON_DISABLED"
    PERSON_ENABLED = "PERSON_ENABLED"
    PERSON_DELETED = "PERSON_DELETED"
    PHOTO_UPLOADED = "PHOTO_UPLOADED"
    PHOTO_DELETED = "PHOTO_DELETED"
    PHOTO_APPROVED = "PHOTO_APPROVED"
    PHOTO_APPROVAL_REVOKED = "PHOTO_APPROVAL_REVOKED"
    ENROLLMENT_REQUESTED = "ENROLLMENT_REQUESTED"
    ENROLLMENT_COMPLETED = "ENROLLMENT_COMPLETED"
    ENROLLMENT_REMOVED = "ENROLLMENT_REMOVED"
    ENROLLMENT_FAILED = "ENROLLMENT_FAILED"
    RECONCILIATION_RUN = "RECONCILIATION_RUN"


# Error codes — the machine-readable contract (contracts/rest-api.md). Never
# collapse distinct failures into a generic one.
class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MEDIA_DECODE_FAILURE = "MEDIA_DECODE_FAILURE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    NO_FACE_DETECTED = "NO_FACE_DETECTED"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    FACE_TOO_SMALL = "FACE_TOO_SMALL"
    QUALITY_REJECTED = "QUALITY_REJECTED"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    DATABASE_FAILURE = "DATABASE_FAILURE"
    FRIGATE_UNAVAILABLE = "FRIGATE_UNAVAILABLE"
    FRIGATE_ENROLLMENT_FAILURE = "FRIGATE_ENROLLMENT_FAILURE"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    PERSON_NOT_FOUND = "PERSON_NOT_FOUND"
    PHOTO_NOT_FOUND = "PHOTO_NOT_FOUND"
    ENROLLED_PERSON_DELETE_REFUSED = "ENROLLED_PERSON_DELETE_REFUSED"
    NOT_READY = "NOT_READY"
    FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"