# Contributing

This project uses [GitHub spec-kit](https://github.com/github/spec-kit) for spec-driven
development — see `CLAUDE.md` for the full `/speckit-*` workflow. This file covers the
engineering process rules that apply on top of that workflow.

## Local Test Documentation Gate

**Every feature must have documented local validation steps before it can be committed as
complete.**

Before committing a feature (new or changed code/config):

1. Identify the feature/spec being changed.
2. Create or update its local testing instructions.
3. Include prerequisites.
4. Include startup commands.
5. Include exact test procedure.
6. Include expected result.
7. Include failure/troubleshooting procedure.
8. Include cleanup/restart instructions.
9. Verify the instructions on the local Mac where practical.
10. Update the feature's validation report.
11. Do not mark a feature complete if its testing documentation is stale.

For this project, feature-local testing documentation lives under `docs/testing/` (e.g.
[`docs/testing/local-mac-testing.md`](docs/testing/local-mac-testing.md) for the Phase 1 Mac
POC environment) and is linked from the corresponding `specs/<feature>/` directory.

**A commit that changes code/config for a feature is incomplete if that feature's local
testing documentation was not reviewed and updated to match.** This applies even when the
change looks small — a config fix, a port remap, a renamed script — if it changes what a
person on the Mac would actually run or see, the doc needs to reflect that.

Sensitive data (credentials, tokens, biometric media, household-identifying information) must
**never** be placed in test documentation. Use placeholders and gitignored paths, and
reference `.env`/secret-management mechanisms rather than pasting real values — consistent
with constitution Principle II.4.

## Pre-commit checklist

Before every commit:

- [ ] `git status` reviewed — nothing unexpected staged
- [ ] `git diff --cached` reviewed line-by-line for anything that looks like a credential,
  token, password, or path to real biometric/media data
- [ ] No `.env` file, secrets, Ring/MQTT/Home Assistant credentials, face photos, sample
  videos, Frigate recordings/snapshots/databases, or other runtime state is staged
- [ ] `.gitignore` still covers every generated/runtime path this change introduces (new bind
  mounts, new services, new config directories) — don't assume an old rule covers a new path
- [ ] **Local Test Documentation Gate** above is satisfied for any feature this commit touches
- [ ] The corresponding `specs/<feature>/validation-report.md` (or equivalent) reflects the
  actual current state — don't leave a stale PASS/FAIL

## Constitution

`.specify/memory/constitution.md` is authoritative for architectural, safety, and privacy
rules. When something in this file or in feature-specific documentation would conflict with
the constitution, the constitution wins — flag the conflict rather than silently resolving it
in either document's favor.
