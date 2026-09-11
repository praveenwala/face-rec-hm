import { useCallback, useState } from 'react'

import { api, ApiError, type EnrollmentMutationResponse } from '../api/client'

// Explicit, human-only enrollment control (Feature 002 Phase 6).
//
// Hard rules:
//  - If the person is NOT READY: render nothing enrollable (no action).
//  - If READY but the backend feature flag is OFF: show "READY FOR ENROLLMENT" plus
//    "Enrollment is disabled by system configuration." The button is disabled and NO
//    request is ever issued.
//  - If the feature flag is ON (future dev/test): require an explicit click, then a
//    deliberate confirmation, before any mutation. Enrollment NEVER happens on render,
//    navigation, refresh, when READY first appears, or after approving a photo.
//
// Feature state (`enrollmentEnabled`) comes from the read-only /api/frigate/status
// endpoint via the caller — it is never inferred from person.enrollment_status.

interface EnrollButtonProps {
  personId: string
  displayName: string
  /** From readiness.status === 'READY' (never inferred from enrollment_status). */
  isReady: boolean
  /** From /api/frigate/status (backend FRIGATE_ENROLLMENT_ENABLED). */
  enrollmentEnabled: boolean
  /** Called after a successful enrollment so the caller can refresh person/readiness. */
  onEnrolled?: (result: EnrollmentMutationResponse) => void
}

type Phase = 'idle' | 'confirming' | 'submitting' | 'error'

const CONFIRM_MESSAGE =
  'Enroll this person in face recognition? This will send the approved enrollment ' +
  'photos to the configured local Frigate instance and create biometric face data.'

export function EnrollButton({
  personId,
  displayName,
  isReady,
  enrollmentEnabled,
  onEnrolled,
}: EnrollButtonProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const submit = useCallback(async () => {
    setPhase('submitting')
    setErrorMessage(null)
    try {
      const result = await api.enrollPerson(personId)
      setPhase('idle')
      onEnrolled?.(result)
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err))
      setPhase('error')
    }
  }, [personId, onEnrolled])

  // Not READY → no enroll action at all.
  if (!isReady) return null

  // READY but disabled by system configuration → visible, non-actionable state.
  if (!enrollmentEnabled) {
    return (
      <div className="enroll-block enroll-disabled">
        <div className="enroll-title">READY FOR ENROLLMENT</div>
        <p className="enroll-hint">Enrollment is disabled by system configuration.</p>
        <button type="button" disabled aria-disabled="true">
          Enroll Approved Photos
        </button>
      </div>
    )
  }

  // Feature flag ON: explicit click → confirmation → mutation.
  if (phase === 'submitting') {
    return (
      <div className="enroll-block">
        <button type="button" disabled>
          Enrolling…
        </button>
      </div>
    )
  }

  if (phase === 'confirming') {
    return (
      <div className="enroll-block enroll-confirm">
        <p className="enroll-confirm-message">{CONFIRM_MESSAGE}</p>
        <div className="enroll-actions">
          <button type="button" className="primary" onClick={() => void submit()}>
            Confirm enrollment
          </button>
          <button type="button" onClick={() => setPhase('idle')}>
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="enroll-block">
      {phase === 'error' && errorMessage && (
        <div className="error-banner">Enrollment failed: {errorMessage}</div>
      )}
      <button type="button" className="primary" onClick={() => setPhase('confirming')}>
        Enroll {displayName} in face recognition
      </button>
    </div>
  )
}
