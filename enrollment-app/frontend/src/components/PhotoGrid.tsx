import { useState } from 'react'

import { api, ApiError, type PhotoDetail, type PhotoSummary } from '../api/client'

interface PhotoGridProps {
  personId: string
  photos: PhotoSummary[]
  onDeleted: (photoId: string) => void
  onApprovalChanged: () => void
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// Human-readable rejection reason — measurements stay separate from judgments (FR-014).
const REASON_LABELS: Record<string, string> = {
  NO_FACE: 'No face detected',
  MULTIPLE_FACES: 'Multiple faces detected',
  FACE_TOO_SMALL: 'Face too small',
  TOO_BLURRY: 'Too blurry',
  UNDEREXPOSED: 'Underexposed',
  OVEREXPOSED: 'Overexposed',
  MEDIA_DECODE_FAILURE: 'Could not decode image',
  UNSUPPORTED_FORMAT: 'Unsupported format',
  FILE_TOO_LARGE: 'File too large',
  STORAGE_FAILURE: 'Storage failure',
  NEAR_DUPLICATE: 'Near duplicate',
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'SUITABLE':
      return 'badge-ok'
    case 'UNSUITABLE':
      return 'badge-error'
    case 'REVIEW_REQUIRED':
      return 'badge-review'
    default:
      return 'badge-pending'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'SUITABLE':
      return '✓ Suitable'
    case 'UNSUITABLE':
      return '✕ Unsuitable'
    case 'REVIEW_REQUIRED':
      return '⚠ Review required'
    default:
      return 'Pending'
  }
}

// Phase 4–5 photo grid: thumbnails + real quality results + explicit approval.
// SUITABLE photos can be APPROVED (human action only — never automatic);
// UNSUITABLE/REVIEW_REQUIRED/PENDING show no approval control (Phase 5 rule #19).
// Multi-face photos explain that a single-person image is required (FR-017).
export default function PhotoGrid({ personId, photos, onDeleted, onApprovalChanged }: PhotoGridProps) {
  const [confirming, setConfirming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState<string | null>(null)
  const [approving, setApproving] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, PhotoDetail | 'loading'>>({})

  const remove = async (photo: PhotoSummary) => {
    try {
      await api.deletePhoto(personId, photo.id)
      setConfirming(null)
      onDeleted(photo.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setConfirming(null)
    }
  }

  const reanalyze = async (photo: PhotoSummary) => {
    setAnalyzing(photo.id)
    setError(null)
    try {
      const detail = await api.analyzePhoto(personId, photo.id)
      setExpanded((prev) => ({ ...prev, [photo.id]: detail }))
      onDeleted(photo.id) // triggers parent refresh of the summary list
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setAnalyzing(null)
    }
  }

  const setApproval = async (photo: PhotoSummary, approved: boolean) => {
    setApproving(photo.id)
    setError(null)
    try {
      if (approved) {
        await api.approvePhoto(personId, photo.id)
      } else {
        await api.unapprovePhoto(personId, photo.id)
      }
      onApprovalChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setApproving(null)
    }
  }

  const toggleDetails = async (photo: PhotoSummary) => {
    if (expanded[photo.id]) {
      setExpanded((prev) => {
        const next = { ...prev }
        delete next[photo.id]
        return next
      })
      return
    }
    setExpanded((prev) => ({ ...prev, [photo.id]: 'loading' }))
    try {
      const detail = await api.getPhoto(personId, photo.id)
      setExpanded((prev) => ({ ...prev, [photo.id]: detail }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setExpanded((prev) => {
        const next = { ...prev }
        delete next[photo.id]
        return next
      })
    }
  }

  if (photos.length === 0) {
    return <p className="empty-state">No photos uploaded yet.</p>
  }

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}
      <div className="photo-grid">
        {photos.map((p) => {
          const reason = p.rejection_reason ? REASON_LABELS[p.rejection_reason] : null
          const isMultiFace = p.rejection_reason === 'MULTIPLE_FACES'
          const detail = expanded[p.id]
          return (
            <div className="photo-card" key={p.id}>
              <img
                className="photo-thumb"
                src={p.thumbnail_url}
                alt={`Uploaded photo ${p.original_filename}`}
                loading="lazy"
              />
              <div className="photo-meta">
                <span className="photo-name" title={p.original_filename}>
                  {p.original_filename}
                </span>
                <span className="photo-dims">
                  {p.width && p.height ? `${p.width}×${p.height} · ` : ''}
                  {formatBytes(p.file_size)}
                </span>
                <span className={`badge ${statusBadgeClass(p.quality_status)}`}>
                  {statusLabel(p.quality_status)}
                  {p.approved ? ' · approved' : ''}
                </span>
                {p.approved && (
                  <span className="badge badge-ok">✓ Approved</span>
                )}
                {reason && (
                  <span className="photo-reason" title={p.rejection_reason ?? undefined}>
                    {reason}
                  </span>
                )}
                {isMultiFace && (
                  <span className="photo-hint">
                    For enrollment, use an image containing only the intended person.
                  </span>
                )}
                {p.quality_status === 'SUITABLE' && p.near_duplicate && (
                  <span className="photo-hint">
                    ⚠ Advisory: visually similar to another uploaded photo — more
                    pose/angle variety is recommended.
                  </span>
                )}
              </div>

              {detail === 'loading' && <p className="photo-detail-note">Loading details…</p>}
              {detail && detail !== 'loading' && (
                <div className="photo-details">
                  <dl>
                    {detail.face_count !== null && (
                      <>
                        <dt>Face count</dt>
                        <dd>{detail.face_count}</dd>
                      </>
                    )}
                    {detail.face_size_ratio !== null && (
                      <>
                        <dt>Face size</dt>
                        <dd>{(detail.face_size_ratio * 100).toFixed(1)}% of image</dd>
                      </>
                    )}
                    {detail.sharpness !== null && (
                      <>
                        <dt>Sharpness</dt>
                        <dd>{detail.sharpness.toFixed(1)}</dd>
                      </>
                    )}
                    {detail.brightness !== null && (
                      <>
                        <dt>Brightness</dt>
                        <dd>{detail.brightness.toFixed(0)} / 255</dd>
                      </>
                    )}
                    {detail.rejection_details && typeof detail.rejection_details.note === 'string' && (
                      <>
                        <dt>Note</dt>
                        <dd>{detail.rejection_details.note}</dd>
                      </>
                    )}
                  </dl>
                </div>
              )}

              <div className="photo-actions">
                <button type="button" onClick={() => void toggleDetails(p)}>
                  {detail ? 'Hide details' : 'Details'}
                </button>
                <button type="button" onClick={() => void reanalyze(p)} disabled={analyzing === p.id}>
                  {analyzing === p.id ? 'Analyzing…' : 'Re-analyze'}
                </button>
                {p.quality_status === 'SUITABLE' && (
                  p.approved ? (
                    <button
                      type="button"
                      onClick={() => void setApproval(p, false)}
                      disabled={approving === p.id}
                    >
                      {approving === p.id ? '…' : 'Unapprove'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void setApproval(p, true)}
                      disabled={approving === p.id}
                    >
                      {approving === p.id ? '…' : 'Approve'}
                    </button>
                  )
                )}
              </div>

              {confirming === p.id ? (
                <div className="photo-confirm">
                  <span>Delete this photo?</span>
                  <button type="button" className="danger" onClick={() => void remove(p)}>
                    Yes, delete
                  </button>
                  <button type="button" onClick={() => setConfirming(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="danger photo-delete"
                  onClick={() => setConfirming(p.id)}
                >
                  Delete
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}