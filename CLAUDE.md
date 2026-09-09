# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository currently contains **no source code** — only a spec-kit (`speckit`) scaffold and the
project's baseline requirements document (`Home_Assistant_Ring_Face_Recognition_Requirements.pdf`).
There is no build, lint, or test tooling to run yet. When implementation work begins (Phase 1 below),
update this section with the actual commands.

## Spec-kit workflow

This project uses [GitHub spec-kit](https://github.com/github/spec-kit) for spec-driven development,
configured for the Claude integration (`.specify/`, `.claude/skills/speckit-*`). Work should flow through
these skills in order, one feature at a time:

1. `/speckit-constitution` — establish/update project principles (`.specify/memory/constitution.md` is
   still the unfilled template — run this before the first real feature if project-wide principles matter).
2. `/speckit-specify` — turn a feature description into `spec.md` for a new feature branch/dir under `specs/`.
3. `/speckit-clarify` — resolve ambiguities in the spec before planning (run before `/speckit-plan` unless
   explicitly skipped).
4. `/speckit-plan` — generate design artifacts (`plan.md`, etc.) from the spec.
5. `/speckit-tasks` — generate a dependency-ordered `tasks.md` from the plan.
6. `/speckit-analyze` — cross-check spec/plan/tasks for consistency (non-destructive, read-only).
7. `/speckit-checklist` — optional, generates a domain-specific quality checklist.
8. `/speckit-implement` — execute `tasks.md` to actually write code.
9. `/speckit-converge` — after manual changes, reconcile the codebase against spec/plan and append any
   missed work back into `tasks.md`.

Each of these is a Claude Code skill (invoke via `/speckit-*`), not a raw script — read the corresponding
`.claude/skills/speckit-*/SKILL.md` if you need the exact procedure it follows.

## Project purpose and target architecture

The goal (full detail in `Home_Assistant_Ring_Face_Recognition_Requirements.pdf`) is to add local person
detection and face recognition to an existing Home Assistant setup, using the Ring Front Door camera:

```
Ring Front Door
  -> Ring cloud / Ring-MQTT bridge (RTSP via go2rtc)
  -> Frigate on a separate compute host (NOT the Raspberry Pi)
  -> person detection -> face recognition (Frigate's native sub-label feature)
  -> known name OR Unknown
  -> relationship mapping (Family / Friend / Neighbor / Other Known) — a manually maintained lookup,
     never inferred from appearance
  -> MQTT -> Home Assistant (on Raspberry Pi 3)
  -> iPhone notification / dashboard / future automation
```

Key hard constraints from the requirements doc — treat these as non-negotiable when designing or
implementing anything in this repo:

- **Home Assistant stays on the Raspberry Pi 3**; Frigate/face recognition must run on separate compute
  and must never be hosted on the Pi.
- **Fail-safe by default**: any uncertain/low-confidence match must resolve to `Unknown`, never a guessed
  identity. Home Assistant automations must keep working even if the AI host is offline.
- **Relationship category is manual metadata** (a name -> category mapping maintained by the user),
  never inferred from facial appearance.
- **Notification-only in this phase** — face recognition must not control locks, alarms, or other
  security-critical actuators.
- **Local-first**: face embeddings, the face library, and Ring/HA credentials stay on local
  infrastructure and are never committed to git or stored in plain text in the project.
- **Apple Silicon limitation**: Frigate's native face recognition requires x86 AVX/AVX2, which Apple
  Silicon Macs lack. An Apple Silicon Mac can validate streaming/MQTT/HA integration/person detection,
  but not native face recognition — only an Intel Mac (or the eventual production host) can do that.

## Implementation phases (from the requirements doc)

Work is expected to proceed in this order; check which phase is current before starting new work:

1. **Phase 0 – Baseline**: existing Ring ding/motion Home Assistant automations (already working).
2. **Phase 1 – Mac POC**: Docker + MQTT + Frigate + a test video source, validating person detection
   without a live Ring stream.
3. **Phase 2 – Ring stream**: add Ring-MQTT/go2rtc, prove live Front Door RTSP ingestion into Frigate.
4. **Phase 3 – Identity**: enable face recognition on supported (AVX/AVX2) hardware, build the face
   library.
5. **Phase 4 – HA intelligence**: identity -> relationship mapping and notifications in Home Assistant.
6. **Phase 5 – Production host**: move Frigate/AI to dedicated hardware (e.g. an Intel mini-PC with
   OpenVINO).
7. **Phase 6 – Expansion**: add other Ring cameras after Front Door accuracy is proven.

This repo is currently pre-Phase-1: no Docker/Frigate config, no face library, and no Home Assistant
automation code exist here yet.
