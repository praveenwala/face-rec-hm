import { useEffect, useState } from 'react'

import { api, type Health } from './api/client'
import AddPersonPage from './pages/AddPersonPage'
import PeoplePage from './pages/PeoplePage'
import PersonDetailPage from './pages/PersonDetailPage'

type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; health: Health }
  | { kind: 'error'; message: string }

function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })
  useEffect(() => {
    api
      .health()
      .then((health) => setState({ kind: 'ok', health }))
      .catch((err: unknown) =>
        setState({
          kind: 'error',
          message: err instanceof Error ? err.message : String(err),
        }),
      )
  }, [])
  return state
}

function HealthBadge({ state }: { state: HealthState }) {
  if (state.kind === 'loading') return <span className="badge badge-pending">checking backend…</span>
  if (state.kind === 'error') return <span className="badge badge-error">backend unreachable: {state.message}</span>
  return (
    <span className="badge badge-ok">
      backend {state.health.status} · db {state.health.database} · v{state.health.app_version}
    </span>
  )
}

// Visibly disabled control — Frigate enrollment is NOT enabled in this phase
// (spec FR-030; the API returns 501 FEATURE_NOT_ENABLED). Clicking it must never
// call the 501 route — it is inert by design (user's Phase 5 rule #21).
function DisabledEnrollmentControl() {
  return (
    <button type="button" disabled title="Frigate enrollment is not enabled in this phase">
      Enrollment not enabled in this phase
    </button>
  )
}

type View =
  | { name: 'people' }
  | { name: 'add' }
  | { name: 'detail'; personId: string }

export default function App() {
  const health = useHealth()
  const [view, setView] = useState<View>({ name: 'people' })

  return (
    <div className="app">
      <header className="app-header">
        <h1>Known Person Enrollment Manager</h1>
        <HealthBadge state={health} />
      </header>

      <main>
        {view.name === 'people' && (
          <PeoplePage
            onAddPerson={() => setView({ name: 'add' })}
            onOpenPerson={(personId) => setView({ name: 'detail', personId })}
          />
        )}
        {view.name === 'add' && <AddPersonPage onDone={() => setView({ name: 'people' })} />}
        {view.name === 'detail' && (
          <PersonDetailPage personId={view.personId} onBack={() => setView({ name: 'people' })} />
        )}

        <section className="placeholder" aria-label="Enrollment status">
          <h2>Enrollment</h2>
          <p>
            Quality analysis (Phase 4), explicit approval, and the readiness gate (Phase 5) are
            live; Frigate enrollment is Phase 6 and stays disabled until then. READY is not
            ENROLLED — reaching READY never triggers any biometric action.
          </p>
          <DisabledEnrollmentControl />
        </section>
      </main>

      <footer className="app-footer">
        <p>
          Localhost-only (127.0.0.1). No biometric data ever leaves this machine; nothing is
          enrolled without an explicit, user-approved action.
        </p>
      </footer>
    </div>
  )
}