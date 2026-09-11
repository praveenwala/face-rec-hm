import { useCallback, useEffect, useState } from 'react'

import {
  api,
  ApiError,
  type FrigateStatusResult,
  type PersonDetail,
  type PhotoSummary,
  type Readiness,
} from '../api/client'

// Coherent person-detail hook built on the canonical HTTP stack (src/api/client.ts).
// It loads the Phase 1–5 data (person + readiness + photos) plus the Phase 6 Frigate
// enrollment feature state in a SINGLE pass. There are no duplicate fetch loops and no
// request-on-every-render: fetching is keyed only on personId, and any refresh after a
// (future) successful enrollment/removal goes through the returned `refresh` callback.
//
// Feature state is taken from the read-only /api/frigate/status endpoint — never
// inferred from person.enrollment_status. While FRIGATE_ENROLLMENT_ENABLED is OFF the
// status resolves to { kind: 'disabled' } (no mutation is ever issued here).

export interface PersonDetailState {
  person: PersonDetail | null
  readiness: Readiness | null
  photos: PhotoSummary[]
  frigate: FrigateStatusResult | null
  loading: boolean
  error: string | null
  /** Convenience: true only when readiness says READY (never inferred elsewhere). */
  isReady: boolean
  /** Convenience: true only when the backend feature flag is enabled. */
  enrollmentEnabled: boolean
  refresh: () => void
}

export function usePersonDetail(personId: string | null): PersonDetailState {
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [photos, setPhotos] = useState<PhotoSummary[]>([])
  const [frigate, setFrigate] = useState<FrigateStatusResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!personId) {
      setPerson(null)
      setReadiness(null)
      setPhotos([])
      setFrigate(null)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      // Single pass. frigateStatusResult never throws on the disabled flag — it maps
      // the FEATURE_NOT_ENABLED refusal to a { kind: 'disabled' } result.
      const [p, rd, ph, fr] = await Promise.all([
        api.getPerson(personId),
        api.getReadiness(personId),
        api.listPhotos(personId),
        api.frigateStatusResult(),
      ])
      setPerson(p)
      setReadiness(rd)
      setPhotos(ph)
      setFrigate(fr)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [personId])

  useEffect(() => {
    void load()
  }, [load])

  const refresh = useCallback(() => {
    void load()
  }, [load])

  const isReady = readiness?.status === 'READY'
  const enrollmentEnabled = frigate?.kind === 'enabled' && frigate.status.enrollment_enabled

  return {
    person,
    readiness,
    photos,
    frigate,
    loading,
    error,
    isReady,
    enrollmentEnabled,
    refresh,
  }
}
