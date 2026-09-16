# Frigate Identity Removal — `train/` Residue Behavior

## Summary

Deleting a face identity in Frigate 0.17.2 removes that identity's **reference** crops (its
`clips/faces/<name>/` folder) but does **not** remove the identity-named **attempt** crops that
Frigate previously saved under `clips/faces/train/`. Those train crops carry the classified
identity in their filename (`<start>-<trackid>-<ts>-<name>-<score>.webp`). On the next recognizer
rebuild (which happens on delete via `recognizer.clear()` and on every Frigate restart), Frigate
re-ingests the `train/` crops, so a **deleted identity can reappear** in the recognizer and match
live faces again.

## How it was discovered

During T035 (Feature 001), a throwaway identity created and "removed" in an earlier test
(`T041_TmpRemove`) re-recognized at ~1.0 against a live clip and competed with the real enrolled
person (score 0.96). Frigate's per-track weighted-average aggregation treats two competing names
as ambiguous and withholds the `sub_label`, so the real person was never assigned. Root cause:
6 `T041_TmpRemove-*.webp` crops had survived in `faces/train/` and were re-taught to the
recognizer on rebuild.

## Fix

`enrollment-app/backend/app/services/frigate_service.py` — `FrigateEnrollmentService.remove_identity`
now performs identity-scoped `train/` cleanup after the HTTP reference delete:

- It deletes ONLY crops whose name-field equals the removed identity, using Frigate's own
  `-`→`_` sanitization so `Foo-Bar` and `Foo_Bar` match.
- It never touches other identities' crops or `unknown` crops.
- It is best-effort and never raises: if the faces dir is not configured
  (`FRIGATE_FACES_DIR` unset) or inaccessible, cleanup is skipped and the reference delete
  still succeeds. The result payload reports `train_artifacts_purged: <count>`.

### Configuration

Set `FRIGATE_FACES_DIR` to the enrollment backend so it can reach Frigate's faces directory
(i.e. `<frigate media>/clips/faces`). When unset, removal behaves as before (reference-only)
and reports `train_artifacts_purged: 0` — no accidental deletion.

## Regression test

`enrollment-app/backend/app/tests/test_removal_train_cleanup.py` (fully offline; synthetic
identity names; empty stub files — no biometric content):

- purges only the removed identity's train crops; preserves unrelated + `unknown` crops;
- after a simulated rebuild (re-scan of `train/`), the deleted identity has zero crops and
  cannot reappear;
- `-`/`_` name-equivalence matching;
- no-faces-dir safe path (0 purged, reference delete still happens).

## Production note

Any production identity-removal / re-enrollment flow MUST purge the identity's `train/` crops
(or the whole `train/` pool) before relying on the recognizer, otherwise a removed or renamed
identity can silently return after the next restart. This also interacts with `save_attempts`
retention: the larger the attempt pool, the more residue can accumulate.
