import { useEffect, useState } from 'react'

import { api, ApiError, type Relationship } from '../api/client'

interface AddPersonPageProps {
  onDone: () => void
}

export default function AddPersonPage({ onDone }: AddPersonPageProps) {
  const [displayName, setDisplayName] = useState('')
  const [relationship, setRelationship] = useState<Relationship>('Family')
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .relationships()
      .then(setRelationships)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err)))
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!displayName.trim()) {
      setError('Display name is required.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.createPerson({ display_name: displayName.trim(), relationship })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <section aria-label="Add Person">
      <div className="toolbar">
        <h2>Add Person</h2>
        <button type="button" onClick={onDone}>
          Back to People
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <form className="form" onSubmit={submit}>
        <label className="form-row">
          <span>Display Name</span>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="e.g. Alex"
            maxLength={100}
            autoFocus
          />
        </label>
        <label className="form-row">
          <span>Relationship</span>
          <select value={relationship} onChange={(e) => setRelationship(e.target.value as Relationship)}>
            {(relationships.length ? relationships : (['Family', 'Friend', 'Neighbor', 'Other Known'] as Relationship[])).map(
              (r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ),
            )}
          </select>
        </label>
        <p className="form-hint">
          Relationship is always user-supplied metadata — it is never inferred from a person's
          appearance.
        </p>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create Person'}
          </button>
        </div>
      </form>

      <p className="modal-hint">
        Photo upload arrives in Phase 3. Creating a person never enrolls biometric data.
      </p>
    </section>
  )
}