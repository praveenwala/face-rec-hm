import { useCallback, useEffect, useState } from 'react'

import { api, ApiError, type PersonSummary, type Relationship } from '../api/client'

// Visual grouping labels vs. stored relationship values (US6). Relationship is
// always user-supplied metadata — never inferred from appearance (spec FR-009).
const GROUPS: { label: string; values: Relationship[] }[] = [
  { label: 'Family', values: ['Family'] },
  { label: 'Friends', values: ['Friend'] },
  { label: 'Neighbors', values: ['Neighbor'] },
  { label: 'Other Known', values: ['Other Known'] },
]

interface PersonCardProps {
  person: PersonSummary
  onOpen: (personId: string) => void
  onEdit: (person: PersonSummary) => void
  onToggleEnabled: (person: PersonSummary) => void
  onDelete: (person: PersonSummary) => void
}

function PersonCard({ person, onOpen, onEdit, onToggleEnabled, onDelete }: PersonCardProps) {
  const initials = (person.display_name.trim()[0] ?? '?').toUpperCase()
  return (
    <div className={`card${person.enabled ? '' : ' card-disabled'}`}>
      <div className="card-avatar" aria-hidden="true">
        {initials}
      </div>
      <div className="card-body">
        <div className="card-title-row">
          <span className="card-name">{person.display_name}</span>
          {!person.enabled && <span className="badge badge-disabled">Disabled</span>}
        </div>
        <div className="card-meta">
          {person.relationship} · {person.photo_count} uploaded photo
          {person.photo_count === 1 ? '' : 's'} · {person.suitable_count} approved suitable
        </div>
        <div className="card-meta">
          <span
            className={`badge ${
              person.enrollment_status === 'READY' ? 'badge-ok' : 'badge-status'
            }`}
          >
            {person.enrollment_status === 'READY' ? 'READY' : person.enrollment_status}
          </span>
          {/* READY is never shown as ENROLLED — Phase 6 has not occurred (rule #22). */}
        </div>
        <div className="card-actions">
          <button type="button" className="primary" onClick={() => onOpen(person.id)}>
            Photos
          </button>
          <button type="button" onClick={() => onEdit(person)}>
            Edit
          </button>
          <button type="button" onClick={() => onToggleEnabled(person)}>
            {person.enabled ? 'Disable' : 'Enable'}
          </button>
          <button type="button" className="danger" onClick={() => onDelete(person)}>
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}

interface EditModalProps {
  person: PersonSummary
  relationships: Relationship[]
  onCancel: () => void
  onSaved: () => void
}

function EditModal({ person, relationships, onCancel, onSaved }: EditModalProps) {
  const [displayName, setDisplayName] = useState(person.display_name)
  const [relationship, setRelationship] = useState<Relationship>(person.relationship)
  const [enabled, setEnabled] = useState(person.enabled)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.updatePerson(person.id, {
        display_name: displayName.trim() || undefined,
        relationship,
        enabled,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Edit ${person.display_name}`}>
        <h3>Edit Person</h3>
        {error && <div className="error-banner">{error}</div>}
        <label className="form-row">
          <span>Display Name</span>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={100}
            autoFocus
          />
        </label>
        <label className="form-row">
          <span>Relationship</span>
          <select value={relationship} onChange={(e) => setRelationship(e.target.value as Relationship)}>
            {relationships.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="form-row form-row-check">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span>Enabled (disable preserves the record; it is not deletion)</span>
        </label>
        <div className="modal-actions">
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="primary" onClick={save} disabled={busy}>
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

interface DeleteModalProps {
  person: PersonSummary
  onCancel: () => void
  onDeleted: () => void
}

function DeleteModal({ person, onCancel, onDeleted }: DeleteModalProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const remove = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.deletePerson(person.id)
      onDeleted()
    } catch (err) {
      // E.g. 409 ENROLLED_PERSON_DELETE_REFUSED (should not occur pre-Phase-6).
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label="Delete person">
        <h3>Delete Person</h3>
        <p className="modal-warning">
          This permanently removes <strong>{person.display_name}</strong> and their local
          metadata record (and uploaded photos, once photo management exists).
        </p>
        <p className="modal-hint">
          Deleting is different from disabling: disabling keeps the record. This action
          cannot be undone.
        </p>
        {error && <div className="error-banner">{error}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="danger" onClick={remove} disabled={busy}>
            Delete Person
          </button>
        </div>
      </div>
    </div>
  )
}

interface PeoplePageProps {
  onAddPerson: () => void
  onOpenPerson: (personId: string) => void
}

export default function PeoplePage({ onAddPerson, onOpenPerson }: PeoplePageProps) {
  const [people, setPeople] = useState<PersonSummary[] | null>(null)
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editing, setEditing] = useState<PersonSummary | null>(null)
  const [deleting, setDeleting] = useState<PersonSummary | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [peopleList, rels] = await Promise.all([api.listPeople(), api.relationships()])
      setPeople(peopleList)
      setRelationships(rels)
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const toggleEnabled = async (person: PersonSummary) => {
    try {
      await api.updatePerson(person.id, { enabled: !person.enabled })
      await refresh()
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : String(err))
    }
  }

  if (loadError && people === null) {
    return <div className="error-banner">Could not load people: {loadError}</div>
  }
  if (people === null) {
    return <div className="empty-state">Loading people…</div>
  }

  const grouped = GROUPS.map((group) => ({
    ...group,
    members: people.filter((p) => group.values.includes(p.relationship)),
  }))
  const hasAnyone = people.length > 0

  return (
    <section aria-label="People">
      <div className="toolbar">
        <h2>People</h2>
        <button type="button" className="primary" onClick={onAddPerson}>
          Add Person
        </button>
      </div>
      {loadError && <div className="error-banner">{loadError}</div>}

      {!hasAnyone && (
        <div className="empty-state">
          No known people yet. Add your first person to start building the known-person library.
        </div>
      )}

      {grouped.map((group) => {
        if (group.members.length === 0) return null
        return (
          <div className="group" key={group.label}>
            <h3 className="group-title">{group.label}</h3>
            <div className="cards">
              {group.members.map((person) => (
                <PersonCard
                  key={person.id}
                  person={person}
                  onOpen={onOpenPerson}
                  onEdit={setEditing}
                  onToggleEnabled={() => void toggleEnabled(person)}
                  onDelete={setDeleting}
                />
              ))}
            </div>
          </div>
        )
      })}

      {editing && (
        <EditModal
          person={editing}
          relationships={relationships}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            void refresh()
          }}
        />
      )}

      {deleting && (
        <DeleteModal
          person={deleting}
          onCancel={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null)
            void refresh()
          }}
        />
      )}
    </section>
  )
}