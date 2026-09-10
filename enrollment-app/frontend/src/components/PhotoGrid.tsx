import { useState } from 'react'

import { api, ApiError, type PhotoSummary } from '../api/client'

interface PhotoGridProps {
  personId: string
  photos: PhotoSummary[]
  onDeleted: (photoId: string) => void
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// Phase 3 photo grid: thumbnails + metadata + delete. Photos show PENDING because
// quality analysis is Phase 4 — never a fabricated SUITABLE/UNSUITABLE label.
export default function PhotoGrid({ personId, photos, onDeleted }: PhotoGridProps) {
  const [confirming, setConfirming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  if (photos.length === 0) {
    return <p className="empty-state">No photos uploaded yet.</p>
  }

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}
      <div className="photo-grid">
        {photos.map((p) => (
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
              <span className="badge badge-status">PENDING</span>
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
              <button type="button" className="danger photo-delete" onClick={() => setConfirming(p.id)}>
                Delete
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}