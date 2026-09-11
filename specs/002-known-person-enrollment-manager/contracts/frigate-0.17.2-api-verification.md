# Frigate 0.17.2 Face API — Verified Contract (G6-PREFLIGHT)

Read-only verification of how enrollment **must** work against the installed Frigate
0.17.2 runtime. This is the evidence base that reconciles
[`frigate-enrollment-interface.md`](./frigate-enrollment-interface.md) with the real API.

**No mutating Frigate call was made to produce this document. No identity, image, or
embedding was created.** This gate verifies the contract; it does **not** perform
enrollment. Phase 6 mutating enrollment code remains BLOCKED pending separate explicit
approval.

> Sanitization: this file contains no personal names, no household photo filenames, no
> per-photo biometric measurements, no API secrets, and no runtime paths tied to a real
> identity. `FACE_DIR` paths below are Frigate's own internal container paths, not app data.

## Runtime verified

| Property | Value | Source |
|---|---|---|
| Version | `0.17.2-3d4dd3a` | `GET /api/version` |
| Image | `ghcr.io/blakeblackshear/frigate:0.17.2` | `docker ps` / compose |
| Digest | `sha256:d4351369984d4a9e2a49ac59736f6490856a7ea11f7790040746d21496967010` | `docker inspect` RepoDigest |
| API base (host) | `http://127.0.0.1:5001` (container port 5000) | `docker port` |
| OpenAPI | `GET /api/openapi.json` → HTTP 200 (~122 KB) | live probe |
| Health | `GET /api/` → "Frigate is running. Alive and healthy!" | live probe |
| Face recognition | `enabled: true`, `model_size: small` | `GET /api/config` |
| Auth | `auth.enabled: true` (cookie `frigate_token`, JWT, roles `admin`/`viewer`) | `GET /api/config` |

Source of truth for behavior: the installed image's
`/opt/frigate/frigate/api/classification.py`,
`/opt/frigate/frigate/embeddings/__init__.py`,
`/opt/frigate/frigate/data_processing/real_time/face.py`,
`/opt/frigate/frigate/data_processing/common/face/model.py`,
`/opt/frigate/frigate/const.py`.

## Verified endpoints (mounted under `/api`)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/faces` | none | — | Lists `{ name: [filenames] }`; `.webp/.png/.jpg/.jpeg`. Empty → `{}`. |
| POST | `/api/faces/{name}/create` | **admin** | — | `mkdir FACE_DIR/{sanitize_filename(name.replace(" ","_"))}`. Quirk: JSON says `success:false` but HTTP 200. |
| POST | `/api/faces/{name}/register` | **admin** | `multipart/form-data`, field **`file`** (binary, required) | Frigate runs its **own** face detection (@0.5 conf), crops, encodes `.webp`, stores under `FACE_DIR/{name}/`, then rebuilds classifier. No face → `{success:false,"No face was detected."}`. |
| POST | `/api/faces/recognize` | none | `multipart/form-data`, field `file` | **Non-persisting** compare. Returns `{success,score,face_name}`. Use for optional post-enroll verification. |
| POST | `/api/faces/{name}/delete` | **admin** | `application/json` `{"ids":[filenames]}` | Deletes listed files; if the folder empties (and name != `train`) the folder is removed → identity gone. Then classifier rebuild. |
| PUT | `/api/faces/{old_name}/rename` | **admin** | `application/json` `{"new_name": "..."}` | Regex + path-traversal validated (see naming). |
| POST | `/api/faces/reprocess` | **admin** | JSON `{training_file}` | Reprocess a `train/` image; not an enrollment path. |
| POST | `/api/faces/train/{name}/classify` | none-guard varies | JSON `{training_file}` or `{event_id}` | Adds a **train-directory file or event snapshot** to a face — **not** an arbitrary client upload. Not the primary enrollment path. |

Request/response schemas (from OpenAPI): `FacesResponse = RootModel[Dict[str,List[str]]]`,
`FaceRecognitionResponse = {success:bool, score:float?, face_name:str?}`,
`DeleteFaceImagesBody = {ids:[str]}`, `RenameFaceBody = {new_name:str}`, register/recognize
multipart bodies expose a single binary `file` field. Error responses: `400` (recognition
disabled / no face), `422` (validation), `500` (processing error), `401/403` (auth/role).

## Enrollment contract (how it must work)

1. **Create identity** — `POST /api/faces/{name}/create` makes the folder; `register` also
   creates it implicitly. The canonical path is: resolve a safe `frigate_identity_name`, then
   `register` one or more images.
2. **Submit a photo** — `POST /api/faces/{name}/register` with `multipart/form-data` `file`.
   Send the **full image**; Frigate detects and crops the face itself. Any cv2-decodable
   format (jpg/png/webp/jpeg). Exactly one clear face expected; images must be sent upright
   (the API does not auto-correct EXIF orientation). Multiple faces are not the intended input.
3. **Internal effect** — the cropped face is written as `.webp` under
   `FACE_DIR/{name}/{name}_{timestamp}.webp` (`FACE_DIR = /media/frigate/clips/faces`).
   Embeddings (ArcFace/FaceNet ONNX) are built **in memory** from the stored crop files; a
   `register`/`delete` triggers `recognizer.clear()`, forcing a rebuild on next classify.
   Effect is immediate; **no restart required**.
4. **Remove identity** — `POST /api/faces/{name}/delete` with the full `ids` list; emptying
   the folder removes the identity. Rename via `PUT /api/faces/{old_name}/rename`.

## Identity naming constraints (verified)

- `create_face`: `sanitize_filename(name.replace(" ", "_"))` — spaces → underscore, path-hostile
  characters stripped.
- `rename_face`: must match regex `^[\p{L}\p{N}\s'_-]{1,50}$` (Unicode letters/digits, space,
  apostrophe, underscore, hyphen; length 1–50) **and** `sanitize_filename(name) == name`, with
  explicit path-traversal guards.
- Names are **directory names** → case sensitivity follows the container filesystem
  (Linux = case-sensitive). Uniqueness = one folder per name.

### Safe future mapping strategy (unchanged, reaffirmed)

| Concept | Owner | Rule |
|---|---|---|
| `Person.id` (UUID) | App | Internal identifier; storage + API references. |
| `display_name` | App | Editable metadata; **never** an identifier. |
| `frigate_identity_name` | App (set at enrollment only) | Must satisfy the regex above; suggested from `display_name` but user-editable; unique against the app table **and** live `GET /api/faces`. A `display_name` rename must **never** rename the Frigate identity. |

## Enrollment photo strategy (recommendation)

- **Let Frigate detect and crop** (option E). Submit **full approved images**, not app-side
  crops — Frigate's detector/encoder owns cropping and must match its recognition pipeline.
- **Submit the approved suitable set individually** (option A), one `register` call per photo,
  because each call stores one crop and the recognizer averages multiple crops per identity
  (`min_faces` gate). Do **not** pre-crop (D) or pre-embed.
- App-side normalization to a canonical JPEG/PNG (option C) is acceptable/benign since Frigate
  re-decodes and re-crops; it is not required by the API.

## Persistence & retention (verified)

- **Source image**: not persisted by `register` — only the **cropped `.webp`** is stored under
  `FACE_DIR/{name}/`.
- **Embeddings**: computed **in memory** from the crop files; not stored as a separate
  persisted embedding blob by the face recognizer (rebuilt on demand).
- **Unknown/recognition attempts**: governed by `save_attempts` (currently **200**). Attempt
  crops (known and unknown) are written to `FACE_DIR/train/{event}-{ts}-{sublabel}-{score}.webp`
  and capped — the oldest is unlinked beyond the cap. This is **separate** from enrolled
  identity folders.
- **Deletion**: `POST /api/faces/{name}/delete` removes the crop files and (when the folder
  empties) the identity folder, then rebuilds the classifier — removing both the stored crops
  and their in-memory embeddings. No separate embedding cleanup step is required.
- **POC caveat**: `/media/frigate` is intentionally **not** bind-mounted, so this data lives
  in the container filesystem and is disposable with the container.

## Required corrections to `frigate-enrollment-interface.md`

| Contract method | Status | Correction |
|---|---|---|
| `health()` | **SUPPORTED AS DESIGNED** | `GET /api/` + `GET /api/version` both confirmed. |
| `list_identities()` | **SUPPORTED AS DESIGNED** | `GET /api/faces` → `{name:[files]}`. |
| `create_identity(name)` | **SUPPORTED** (minor) | `POST /api/faces/{name}/create`; expect the `success:false`-but-200 quirk; treat HTTP 200 as success. |
| `register_face(name, image)` | **SUPPORTED — with correction** | `multipart/form-data`, field **`file`**, **full image** (Frigate crops). Requires **admin** role. |
| `train_face(name, file\|event_id)` | **NEEDS CORRECTION** | Not a client-upload path — accepts only a `train/` dir file or an `event_id`. Not the enrollment path; keep out of the enroll flow. |
| `remove_identity(name)` | **SUPPORTED — with correction** | `POST /api/faces/{name}/delete` with the **full `ids` list** (must first `GET /api/faces` to enumerate files). Requires **admin**. |
| `reprocess(name)` | **SUPPORTED** (niche) | `POST /api/faces/reprocess` operates on a `train/` file; not needed for normal enroll. |
| `recognize(image)` | **SUPPORTED AS DESIGNED** | `POST /api/faces/recognize`, non-persisting; optional post-enroll verification. |
| `reindex()` | **UNSUPPORTED (drop)** | `PUT /api/reindex` requires `semantic_search.enabled` and reindexes **tracked-object** embeddings, **not** the face library. Face embeddings rebuild automatically after `register`/`delete`. Remove `reindex()` from the enrollment flow. |
| `reconcile()` | **SUPPORTED AS DESIGNED** | Read-only diff of app persons vs `GET /api/faces`; never auto-mutates. |

**Auth correction (new):** every mutating face endpoint (`create`, `register`, `delete`,
`rename`, `reprocess`) requires `require_role(["admin"])`. The service must authenticate with
an admin-role credential; the contract currently omits auth.

## Final proposed service surface (validated)

`inspect (list_identities/health)`, `create_identity`, `register_face (full image, admin)`,
`remove_identity (enumerate then delete all ids, admin)`, `rename_identity`,
`recognize (verify, optional)`, `reconcile (read-only diff)`. No `reindex`. No invented
endpoints.
