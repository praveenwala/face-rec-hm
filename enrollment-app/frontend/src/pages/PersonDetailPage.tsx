import { useCallback, useEffect, useState } from 'react'

import { api, ApiError, type PersonDetail, type PhotoSummary } from '../api/client'
import PhotoGrid from '../components/PhotoGrid'
import UploadDropzone from '../components/UploadDropzone'

interface PersonDetailPageProps {
  personId: string
  onBack: () => void
}

// Phase 3–4 person detail: metadata + private photo management (US2/US5) + automatic
// per-photo quality analysis (US3). Approval and readiness are Phase 5; Frigate
// enrollment is Phase 6 (never presented here as available).
export default function PersonDetailPage({ personId, onBack }: PersonDetailPageProps) {
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [photos, setPhotos] = useState<PhotoSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [p, ph] = await Promise.all([
        api.getPerson(personId),
        api.listPhotos(personId),
      ])
      setPerson(p)
      setPhotos(ph)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    }
  }, [personId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (error && person === null) {
    return (
      <section aria-label="Person detail">
        <div className="toolbar">
          <button type="button" onClick={onBack}>
            ← Back to People
          </button>
        </div>
        <div className="error-banner">Could not load person: {error}</div>
      </section>
    )
  }
  if (person === null) {
    return <div className="empty-state">Loading person…</div>
  }

  return (
    <section aria-label="Person detail">
      <div className="toolbar">
        <h2>{person.display_name}</h2>
        <button type="button" onClick={onBack}>
          ← Back to People
        </button>
      </div>

      <div className="detail-meta">
        <span className="badge badge-status">{person.relationship}</span>
        <span className="badge badge-status">{person.enrollment_status}</span>
        {!person.enabled && <span className="badge badge-disabled">Disabled</span>}
        <span>
          {photos.length} photo{photos.length === 1 ? '' : 's'} uploaded ·{' '}
          {person.suitable_count} suitable-approved
        </span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <UploadDropzone personId={personId} onUploaded={() => void refresh()} />

      <div className="section-block">
        <h3>Photos</h3>
        <PhotoGrid personId={personId} photos={photos} onDeleted={() => void refresh()} />
      </div>

      <p className="modal-hint">
        Photos are stored privately on this machine only. Quality analysis runs automatically
        on upload (face count, size, sharpness, brightness). Explicit approval and readiness
        (Phase 5) come next; Frigate enrollment is not enabled in this phase. A suitable photo
        is never auto-approved or auto-enrolled.
      </p>
    </section>
  )
}