import { useEffect, useState } from 'react'

import { api, type Health } from './api/client'
import AddPersonPage from './pages/AddPersonPage'
import PeoplePage from './pages/PeoplePage'

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
// (spec FR-030; the API returns 501 FEATURE_NOT_ENABLED).
function DisabledEnrollmentControl() {
  return (
    <button type="button" disabled title="Frigate enrollment is not enabled in this phase">
      Enrollment not enabled in this phase
    </button>
  )
}

type View = 'people' | 'add'

export default function App() {
  const health = useHealth()
  const [view, setView] = useState<View>('people')

  return (
    <div className="app">
      <header className="app-header">
        <h1>Known Person Enrollment Manager</h1>
        <HealthBadge state={health} />
      </header>

      <main>
        {view === 'people' ? (
          <PeoplePage onAddPerson={() => setView('add')} />
        ) : (
          <AddPersonPage onDone={() => setView('people')} />
        )}

        <section className="placeholder" aria-label="Enrollment status">
          <h2>Enrollment</h2>
          <p>
            Photo upload, quality checks, approval, and readiness arrive in Phases 3–5.
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