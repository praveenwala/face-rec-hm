import { useRef, useState } from 'react'

import { api, ApiError, type UploadResult } from '../api/client'

interface UploadDropzoneProps {
  personId: string
  onUploaded: () => void
}

// Multi-file drag-and-drop + file-picker upload (Phase 3, T020). Every file in the
// batch gets its own visible result — accepted (PENDING) or rejected with an explicit
// reason. Uploading never approves or enrolls anything (FR-019/FR-022).
export default function UploadDropzone({ personId, onUploaded }: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<UploadResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files)
    if (list.length === 0) return
    setBusy(true)
    setError(null)
    setResults([])
    try {
      const res = await api.uploadPhotos(personId, list)
      setResults(res)
      onUploaded()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="upload-section">
      <div
        className={`dropzone${dragging ? ' dropzone-active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          void handleFiles(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload photos"
      >
        <p>Drag photos here, or click to choose files</p>
        <p className="form-hint">JPEG, PNG, or WEBP · multi-file supported · nothing is enrolled</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          hidden
          onChange={(e) => e.target.files && void handleFiles(e.target.files)}
        />
        {busy && <p className="badge badge-pending">Uploading…</p>}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {results.length > 0 && (
        <ul className="upload-results" aria-label="Upload results">
          {results.map((r, i) => (
            <li key={`${r.original_filename}-${i}`} className={r.photo_id ? 'result-ok' : 'result-rejected'}>
              <span className="result-name">{r.original_filename}</span>
              {r.photo_id ? (
                <span className="badge badge-status">PENDING — stored, not yet analyzed</span>
              ) : (
                <span className="badge badge-error">Rejected: {r.rejection_reason ?? 'unknown'}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}