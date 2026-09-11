# Real Enrollment Checklist (G6)

This checklist must be completed **before** any real biometric enrollment is executed.
Items are not automatically marked complete because code exists.

## Implementation gate

- [ ] G6 implementation PASS
- [ ] Enrollment feature flag explicitly enabled (`FRIGATE_ENROLLMENT_ENABLED=true`)
- [ ] User explicitly authorizes biometric enrollment

## Person readiness

- [ ] Person READY
- [ ] >= 5 distinct approved suitable images
- [ ] Current Frigate face library inspected (`GET /api/faces`)
- [ ] No identity conflict (target identity absent on live Frigate)

## Frigate operational readiness

- [ ] Frigate authentication working (admin-role credential verified)
- [ ] Frigate face recognition enabled and observable
- [ ] Rollback path tested
- [ ] Retention policy reviewed (`save_attempts`, unknown-face crop retention)
- [ ] Network exposure reviewed (management API bound only where intended)
- [ ] Backup/recovery implications reviewed

## Cross-feature authorization

- [ ] Feature 001 T034 separately authorized, if real identity enrollment is intended through that path

## Audit / privacy

- [ ] No real household image submitted to Frigate during implementation gate
- [ ] No runtime DB, models, or credentials committed to source control

## Notes

- `READY` is not `ENROLLED`. Readiness means the local manager has a sufficient
  explicitly approved photo set; it never triggers enrollment, embeddings, identity
  creation, or any Frigate/HA/MQTT action.
- Enrollment creates persisted Frigate face crops. Unknown face attempts may also be
  retained according to `save_attempts`. Both retention behaviors must be reviewed
  before real enrollment.
