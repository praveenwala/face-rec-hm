import { useCallback, useEffect, useState } from 'react'

import {
  api,
  ApiError,
  type FrigateStatusResult,
  type PersonDetail,
  type PhotoSummary,
  type Readiness,
} from '../api/client'
import { EnrollButton } from '../components/EnrollButton'
import PhotoGrid from '../components/PhotoGrid'
import UploadDropzone from '../components/UploadDropzone'

interface PersonDetailPageProps {
  personId: string
  onBack: () => void
}

// Phase 3–5 person detail: metadata + private photo management (US2/US5) +
// automatic quality analysis (US3) + explicit approval and the readiness gate
// (US4). READY is clearly distinguished from ENROLLED — Frigate enrollment is
// Phase 6 and never presented here as available.
export default function PersonDetailPage({ personId, onBack }: PersonDetailPageProps) {
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [photos, setPhotos] = useState<PhotoSummary[]>([])
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [frigate, setFrigate] = useState<FrigateStatusResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [p, ph, rd, fr] = await Promise.all([
        api.getPerson(personId),
        api.listPhotos(personId),
        api.getReadiness(personId),
        api.frigateStatusResult(),
      ])
      setPerson(p)
      setPhotos(ph)
      setReadiness(rd)
      setFrigate(fr)
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

  const isReady = readiness?.status === 'READY'

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
        <span className={`badge ${isReady ? 'badge-ok' : 'badge-status'}`}>
          {readiness?.status ?? person.enrollment_status}
        </span>
        {!person.enabled && <span className="badge badge-disabled">Disabled</span>}
        <span>
          {photos.length} photo{photos.length === 1 ? '' : 's'} uploaded ·{' '}
          {readiness?.approved_suitable_count ?? person.suitable_count} approved suitable
        </span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Phase 5 readiness card — READY is permission to consider enrollment, never ENROLLED */}
      {readiness && (
        <div className={`readiness-card${isReady ? ' readiness-ready' : ''}`}>
          <div className="readiness-head">
            <h3>Enrollment Readiness</h3>
            <span className={`badge ${isReady ? 'badge-ok' : 'badge-status'}`}>
              {isReady ? 'READY FOR ENROLLMENT' : 'NOT READY'}
            </span>
          </div>
          <p className="readiness-count">
            {readiness.approved_suitable_count} / {readiness.minimum_required} approved
            suitable photos
          </p>
          {!isReady ? (
            <p className="readiness-hint">
              {readiness.remaining_required > 0
                ? `${readiness.remaining_required} more approved suitable photo${
                    readiness.remaining_required === 1 ? '' : 's'
                  } required.`
                : 'No photos uploaded yet.'}
            </p>
          ) : readiness.near_duplicate_advisory ? (
            <p className="readiness-hint">
              Some approved photos are visually similar. Consider adding more
              pose/expression variety before enrollment.
            </p>
          ) : (
            <p className="readiness-hint">
              Recommended: add more pose/expression variety before enrollment.
            </p>
          )}
          {isReady && <p className="readiness-hint">Biometric enrollment is disabled in this phase.</p>}
        </div>
      )}

      {/* Phase 6 enrollment control — feature state comes from /api/frigate/status,
          never inferred from enrollment_status. While the backend flag is OFF this
          renders the disabled "READY FOR ENROLLMENT" state and issues no request. */}
      {isReady && (
        <div className="section-block">
          <h3>Frigate Enrollment</h3>
          <EnrollButton
            personId={personId}
            displayName={person.display_name}
            isReady={isReady}
            enrollmentEnabled={
              frigate?.kind === 'enabled' && frigate.status.enrollment_enabled
            }
            onEnrolled={() => void refresh()}
          />
        </div>
      )}

      <UploadDropzone personId={personId} onUploaded={() => void refresh()} />

      <div className="section-block">
        <h3>Photos</h3>
        <PhotoGrid
          personId={personId}
          photos={photos}
          onDeleted={() => void refresh()}
          onApprovalChanged={() => void refresh()}
        />
      </div>

      <p className="modal-hint">
        Photos are stored privately on this machine only. Quality analysis runs automatically;
        approval is an explicit action and never happens automatically. A READY badge means the
        local set is sufficient — it is not enrollment, and it never triggers any biometric
        action.
      </p>
    </section>
  )
}