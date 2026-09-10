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
  thumbnail_url: string
  created_at: string | null
}

export interface PhotoDetail extends PhotoSummary {
  measurements: Record<string, unknown> | null
  rejection_details: Record<string, unknown> | null
  duplicate_group: string | null
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

  audit: (personId?: string) => {
    const q = personId ? `?person_id=${encodeURIComponent(personId)}` : ''
    return request<{ entries: AuditEntry[] }>(`/api/audit${q}`).then((r) => r.entries)
  },
}