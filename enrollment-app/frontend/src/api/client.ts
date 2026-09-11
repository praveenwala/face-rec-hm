// Typed fetch wrapper against contracts/rest-api.md. Every error response carries
// the documented envelope: { error: { code, message, details } }.

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message)
    this.status = status
    this.code = body.error.code
    this.details = body.error.details ?? {}
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init)
  if (!resp.ok) {
    let body: ApiErrorBody
    try {
      body = (await resp.json()) as ApiErrorBody
    } catch {
      body = { error: { code: 'INTERNAL_ERROR', message: `HTTP ${resp.status}` } }
    }
    throw new ApiError(resp.status, body)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export interface Health {
  status: string
  app_version: string
  database: string
  frigate: { reachable: boolean | null }
}

// The four user-supplied relationship categories (spec FR-004; GET /api/relationships).
export type Relationship = 'Family' | 'Friend' | 'Neighbor' | 'Other Known'

export interface PersonSummary {
  id: string
  display_name: string
  relationship: Relationship
  enabled: boolean
  enrollment_status: string
  suitable_count: number
  photo_count: number
  representative_photo_url: string | null
}

export interface PersonDetail extends PersonSummary {
  frigate_identity_name: string | null
  representative_photo_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface PhotoSummary {
  id: string
  person_id: string
  original_filename: string
  mime_type: string
  width: number | null
  height: number | null
  file_size: number
  quality_status: string
  approved: boolean
  rejection_reason: string | null
  enrolled_in_frigate: boolean
  near_duplicate: { distance: number; threshold: number; photo_id: string } | null
  thumbnail_url: string
  created_at: string | null
}

export interface PhotoDetail extends PhotoSummary {
  face_count: number | null
  face_size_ratio: number | null
  sharpness: number | null
  brightness: number | null
  measurements: Record<string, unknown> | null
  rejection_details: Record<string, unknown> | null
  duplicate_group: string | null
}

export interface Readiness {
  person_id: string
  status: string // DRAFT | NOT_READY | READY
  minimum_required: number
  required_min: number
  approved_suitable_count: number
  suitable_count: number
  remaining_required: number
  total_uploaded: number
  approved_count: number
  review_required_count: number
  unsuitable_count: number
  pending_count: number
  enrollment_enabled: boolean
  near_duplicate_advisory: boolean
  missing: string[]
  diversity: Record<string, unknown>
}

export interface UploadResult {
  photo_id: string | null
  original_filename: string
  quality_status: string | null
  rejection_reason: string | null
  measurements: Record<string, unknown> | null
  approved: boolean
}

export interface AuditEntry {
  id: number
  timestamp: string
  action: string
  entity_type: string | null
  entity_id: string | null
  details: Record<string, unknown> | null
}

export interface CreatePersonInput {
  display_name: string
  relationship: Relationship
}

export interface UpdatePersonInput {
  display_name?: string
  relationship?: Relationship
  enabled?: boolean
}

// --- Feature 002 Phase 6 (enrollment) — matches backend enrollment routes ---
//
// All three endpoints are gated by FRIGATE_ENROLLMENT_ENABLED on the backend. While
// the flag is OFF they return the canonical error envelope with code
// FEATURE_NOT_ENABLED (HTTP 501); the frontend must render the disabled state rather
// than issue mutations. Do NOT infer feature state from person.enrollment_status.

// Read-only status snapshot returned when the feature is enabled. While disabled the
// endpoint refuses with FEATURE_NOT_ENABLED (surfaced as ApiError), so callers treat a
// FEATURE_NOT_ENABLED error as "enrollment disabled by system configuration".
export interface FrigateStatus {
  enrollment_enabled: boolean
  frigate_reachable: boolean | null
  api_url: string
  identities: string[] | null
}

export interface EnrollmentMutationResponse {
  person_id: string
  enrollment_status: string
  frigate_identity_name: string | null
}

// Discriminated feature-state result so the UI never has to catch-and-inspect inline.
export type FrigateStatusResult =
  | { kind: 'enabled'; status: FrigateStatus }
  | { kind: 'disabled'; reason: string }
  | { kind: 'error'; error: ApiError }

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export const api = {
  health: () => request<Health>('/api/health'),

  relationships: () =>
    request<{ relationships: Relationship[] }>('/api/relationships').then(
      (r) => r.relationships,
    ),

  listPeople: () =>
    request<{ people: PersonSummary[] }>('/api/people').then((r) => r.people),

  getPerson: (id: string) => request<PersonDetail>(`/api/people/${id}`),

  createPerson: (input: CreatePersonInput) =>
    request<PersonDetail>('/api/people', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    }),

  updatePerson: (id: string, input: UpdatePersonInput) =>
    request<PersonDetail>(`/api/people/${id}`, {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    }),

  deletePerson: (id: string) =>
    request<void>(`/api/people/${id}`, { method: 'DELETE' }),

  listPhotos: (personId: string) =>
    request<{ photos: PhotoSummary[] }>(`/api/people/${personId}/photos`).then(
      (r) => r.photos,
    ),

  uploadPhotos: (personId: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f, f.name))
    return request<{ results: UploadResult[] }>(`/api/people/${personId}/photos`, {
      method: 'POST',
      body: form,
    }).then((r) => r.results)
  },

  getPhoto: (personId: string, photoId: string) =>
    request<PhotoDetail>(`/api/people/${personId}/photos/${photoId}`),

  deletePhoto: (personId: string, photoId: string) =>
    request<void>(`/api/people/${personId}/photos/${photoId}`, { method: 'DELETE' }),

  analyzePhoto: (personId: string, photoId: string) =>
    request<PhotoDetail>(`/api/people/${personId}/photos/${photoId}/analyze`, {
      method: 'POST',
    }),

  approvePhoto: (personId: string, photoId: string) =>
    request<PhotoDetail>(`/api/people/${personId}/photos/${photoId}/approve`, {
      method: 'POST',
    }),

  unapprovePhoto: (personId: string, photoId: string) =>
    request<PhotoDetail>(`/api/people/${personId}/photos/${photoId}/unapprove`, {
      method: 'POST',
    }),

  getReadiness: (personId: string) =>
    request<Readiness>(`/api/people/${personId}/readiness`),


  audit: (personId?: string) => {
    const q = personId ? `?person_id=${encodeURIComponent(personId)}` : ''
    return request<{ entries: AuditEntry[] }>(`/api/audit${q}`).then((r) => r.entries)
  },

  // --- Phase 6 (enrollment) ---

  // Raw status call: resolves when enabled, throws ApiError (FEATURE_NOT_ENABLED)
  // while the feature flag is OFF.
  frigateStatus: () => request<FrigateStatus>('/api/frigate/status'),

  // Convenience wrapper that turns the FEATURE_NOT_ENABLED refusal into an explicit
  // "disabled" result instead of a thrown error, so callers can render feature state
  // without inspecting exceptions. Never issues a mutation.
  frigateStatusResult: async (): Promise<FrigateStatusResult> => {
    try {
      const status = await request<FrigateStatus>('/api/frigate/status')
      return { kind: 'enabled', status }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'FEATURE_NOT_ENABLED') {
        return { kind: 'disabled', reason: err.message }
      }
      if (err instanceof ApiError) return { kind: 'error', error: err }
      throw err
    }
  },

  // Mutation — only ever called from an explicit, confirmed user action. While the
  // backend flag is OFF this rejects with ApiError(FEATURE_NOT_ENABLED) and performs
  // no Frigate mutation.
  enrollPerson: (personId: string) =>
    request<EnrollmentMutationResponse>(
      `/api/people/${encodeURIComponent(personId)}/enroll`,
      { method: 'POST', headers: JSON_HEADERS },
    ),

  removeEnrollment: (personId: string) =>
    request<EnrollmentMutationResponse>(
      `/api/people/${encodeURIComponent(personId)}/enrollment`,
      { method: 'DELETE' },
    ),
}