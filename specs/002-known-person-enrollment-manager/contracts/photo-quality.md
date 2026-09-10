# Contract: Photo Quality Validation

The objective validation pipeline applied to every uploaded enrollment photo (spec FR-012 –
FR-017; feature 001's T034 media gate concepts adapted). This contract fixes the quality
states, rejection reasons, pipeline order, readiness rule, multi-face policy, and the
objective-vs-heuristic boundary. Threshold values below are **initial conservative defaults,
explicitly not claimed as tuned** — the same stance feature 001 took for recognition
thresholds at T033 (`DEFERRED_UNTIL_ENROLLMENT`). They are configuration constants in the
backend (`QualityConfig`), tunable after validation against real household photos.

## Pipeline (per file, in order)

```text
1. Size check            → reject if > MAX_UPLOAD_BYTES (default 20 MB)
2. Content sniff          → mime_type by magic bytes (never extension alone);
                            HEIC/HEIF detected here stays UNSUPPORTED_FORMAT (see below)
3. Pillow decode          → fail → MEDIA_DECODE_FAILURE (corrupt/truncated/unknown)
4. EXIF orientation       → record raw orientation; apply exif_transpose before measuring
5. Face detection         → Frigate's facedet.onnx (YuNet) via OpenCV FaceDetectorYN;
                            score_threshold aligned to Frigate's detection_threshold (0.7);
                            detector missing/unloadable → FACE_DETECTOR_UNAVAILABLE
                            (NO silent fallback detector — user-approved Phase 4 decision)
6. face_count == 0        → UNSUITABLE (NO_FACE)
7. face_count > 1         → REVIEW_REQUIRED (MULTIPLE_FACES)   ← hard stop, no auto-select
8. face too small         → UNSUITABLE (FACE_TOO_SMALL)
9. sharpness too low      → UNSUITABLE (TOO_BLURRY)
10. brightness out of range → UNSUITABLE (UNDEREXPOSED | OVEREXPOSED)
11. near-duplicate check  → REVIEW_REQUIRED (NEAR_DUPLICATE)   [Phase 5, where practical]
12. all pass              → SUITABLE
```

Steps 1–10 are always executed (Phase 4). Step 11 is added in Phase 5. Nothing in this
pipeline ever compares the photo against enrolled identities (FR-013 — no identity inference
during quality validation). Classification precedence is exactly the order above — if
multiple problems exist the FIRST blocking reason in this order is the canonical
`rejection_reason`; all measurements are retained regardless (objective vs. heuristic split,
FR-014).

## Quality states

| Status | Meaning | Usable for enrollment? |
|---|---|---|
| `PENDING` | Processing in progress | No |
| `SUITABLE` | Passed all checks; exactly one usable face | Yes, once explicitly approved |
| `UNSUITABLE` | Failed a blocking check | No |
| `REVIEW_REQUIRED` | Needs human review (multi-face, near-duplicate) | No (until resolved) |

## Rejection reasons (canonical enum)

| Code | Meaning | Maps from |
|---|---|---|
| `NO_FACE` | Decoded fine; zero faces detected | pipeline step 7 |
| `MULTIPLE_FACES` | More than one face detected; not silently accepted | step 8 |
| `FACE_TOO_SMALL` | Primary face below the minimum size | step 9 |
| `TOO_BLURRY` | Laplacian variance below threshold | step 10 |
| `UNDEREXPOSED` | Mean face luminance below minimum | step 11 |
| `OVEREXPOSED` | Mean face luminance above maximum | step 11 |
| `MEDIA_DECODE_FAILURE` | File could not be decoded (corrupt/truncated/unknown) | step 3 |
| `UNSUPPORTED_FORMAT` | Recognized content outside the application allowlist, or HEIC/HEIF (normalization deferred) | ingestion (Phase 3) |
| `FACE_DETECTOR_UNAVAILABLE` | The approved YuNet model is missing/unloadable — analysis fails cleanly (no silent fallback); uploads stay PENDING with an explicit `analysis_error`, re-analysis returns 503 | step 5 |
| `NEAR_DUPLICATE` | Perceptual hash too close to an existing photo of the same person | step 12 (Phase 5) |
| `FILE_TOO_LARGE` | Ingestion-level: upload exceeds `MAX_UPLOAD_BYTES` — rejected before any decode | step 1 |
| `STORAGE_FAILURE` | Ingestion-level: could not write the file to private storage | steps 4–6 (write path) |

`FILE_TOO_LARGE` and `STORAGE_FAILURE` are ingestion-level per-file results (Phase 3), not
quality classifications — they never imply anything about the image content. A rejected
file is never stored and gets no DB row.

`MEDIA_DECODE_FAILURE`/`UNSUPPORTED_FORMAT` are **never** collapsed into `NO_FACE` (spec
FR-016; feature 001's §10 media policy makes the same distinction). A photo carries one canonical
`rejection_reason`; secondary reasons and raw measurements go in `rejection_details`
(JSON), never in the reason enum.

## Objective measurements vs. heuristics

| Measurement | Type | Notes |
|---|---|---|
| width, height, file_size, mime_type, orientation | Objective | Recorded exactly as measured |
| face_count | Objective | Count of detections above score threshold |
| face_size_ratio | Objective | Primary face box area / image area (+ per-axis ratios) |
| sharpness (Laplacian variance) | Objective | Variance over the grayscale face crop |
| brightness (mean luminance 0–255) | Objective | Mean over the face crop |
| perceptual hash (Phase 5) | Objective | pHash value + distance to nearest same-person photo |

| Judgment | Type | Notes |
|---|---|---|
| "SUITABLE / UNSUITABLE" | Derived | Threshold application over the measurements |
| "UNDEREXPOSED / OVEREXPOSED" | Derived | Label for luminance out of configured range — **never** phrased as "night"/"daylight" or any unmeasured semantic |
| diversity/angle/expression notes | Review metadata | User-reviewable notes only; not blocking in the MVP |

The UI must render the two groups separately (spec US3 scenario 6, FR-014).

## Default thresholds (QualityConfig — INITIAL POC BASELINES, NOT PRODUCTION-TUNED)

```text
MAX_UPLOAD_BYTES          = 20 * 1024 * 1024
MIN_FACE_AREA_RATIO       = 0.01        # face box / image area
MIN_FACE_WIDTH_RATIO      = 0.08        # face box width / image width
MIN_FACE_HEIGHT_RATIO     = 0.08        # face box height / image height
MIN_FACE_DETECT_SCORE     = 0.7         # aligned with Frigate detection_threshold
MIN_SHARPNESS_LAPLACIAN   = 40.0        # variance over face crop (grayscale)
BRIGHTNESS_MIN            = 40.0        # mean luminance 0-255
BRIGHTNESS_MAX            = 220.0
DUP_HASH_DISTANCE         = 8           # pHash 16x16 hamming distance (Phase 5)
```

Any value may be tuned after real-photo validation; tuning MUST be recorded in the audit log
and in the validation report, never silently (constitution II.2, V.4).

## Readiness rule

```text
suitable_count = count(photos where quality_status == SUITABLE AND approved == true)
required_min   = 5   (matches feature 001's T034 gate)

status = DRAFT      if no photos
       = NOT_READY  if suitable_count < 5
       = READY      if suitable_count >= 5
```

- `UNSUITABLE`, `REVIEW_REQUIRED`, and unapproved photos never count (spec US4 scenario 3).
- `READY` never triggers enrollment (FR-022, SC-006). Enrollment is only the explicit
  "Enroll Approved Photos" action (Phase 6).

## Detector unavailability policy (explicit, user-approved)

- The ONLY approved detector is the Frigate-aligned `facedet.onnx` (YuNet via OpenCV
  `FaceDetectorYN`) used by the validated local Frigate 0.17.2 environment — so a photo
  accepted here is likely to produce a usable face when that validated environment processes
  it (the T034 media-gate objective). No claim of broader compatibility with every Frigate
  installation/version is made.
- If the model file is missing or cannot be loaded, analysis **fails cleanly** with
  `FACE_DETECTOR_UNAVAILABLE` — there is NO silent fallback to Haar or any other detector
  (readiness semantics must never silently change depending on which detector happened to
  load). A fallback detector may be evaluated later only with explicit approval.
- On upload, a missing detector degrades gracefully: the photo is still stored, stays
  `PENDING`, and carries an explicit `analysis_error` in `measurements`. The explicit
  re-analysis endpoint returns `503 FACE_DETECTOR_UNAVAILABLE`. No fabricated classification
  is ever produced.

## Multi-face policy (explicit)

- **Preferred**: exactly one usable face per enrollment photo.
- `face_count > 1` → `REVIEW_REQUIRED` with reason `MULTIPLE_FACES`. The system does **not**
  silently choose the largest/central face, does not crop, and does not mark the photo
  suitable.
- The user resolves it by providing a cleaner image or deleting the photo. Automatic
  face selection/cropping is a documented future feature, out of MVP scope (spec FR-017).

## Media support statement

- Application upload allowlist (Phase 3, user-approved): **exactly JPEG, PNG, WEBP** —
  decided by decoded/sniffed content (magic bytes + decode), never by filename extension.
  Valid images outside the allowlist (BMP, GIF, TIFF, and other Pillow-decodable formats)
  are rejected with `UNSUPPORTED_FORMAT` for the predictable enrollment-media workflow.
- HEIC/HEIF: detected by content (`ftyp` brand) and rejected with `UNSUPPORTED_FORMAT`
  (note: convert to JPEG/PNG/WEBP). Normalization via ffmpeg (research.md #6) is deferred
  pending explicit approval — no silent normalization, no `normalized/` artifact in
  Phase 4 (`kind=normalized` returns 404). The original file is never modified
  (FR-011/FR-018).
- No universal format support is claimed — decode success is the test, exactly as in feature
  001's media policy (local-mac-testing.md §10).