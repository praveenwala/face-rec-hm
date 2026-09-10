import { useEffect, useState } from 'react'

import { api, type Health } from './api/client'

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

export default function App() {
  const health = useHealth()

  return (
    <div className="app">
      <header className="app-header">
        <h1>Known Person Enrollment Manager</h1>
        <HealthBadge state={health} />
      </header>

      <main>
        <section className="placeholder" aria-label="People page placeholder">
          <h2>People</h2>
          <p>
            Known people grouped by relationship (Family · Friends · Neighbors · Other Known)
            arrive in Phase 2.
          </p>
        </section>

        <section className="placeholder" aria-label="Add person placeholder">
          <h2>Add Person</h2>
          <p>Create a known person with a display name and a user-supplied relationship.</p>
          <DisabledEnrollmentControl />
        </section>

        <section className="placeholder" aria-label="Person detail placeholder">
          <h2>Person Detail</h2>
          <p>Photo upload, quality status, approval, and readiness arrive in Phases 3–5.</p>
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