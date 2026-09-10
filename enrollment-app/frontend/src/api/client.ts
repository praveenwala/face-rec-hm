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

export const api = {
  health: () => request<Health>('/api/health'),
}