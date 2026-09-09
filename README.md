# Home Assistant Ring Face Recognition

Local-first person detection and face recognition for an existing Home Assistant setup, using
the Ring Front Door camera. Full context: [`CLAUDE.md`](CLAUDE.md) and the ratified
[project constitution](.specify/memory/constitution.md).

This project uses [spec-kit](https://github.com/github/spec-kit) for spec-driven development.
The active feature is
[`001-front-door-person-identification`](specs/001-front-door-person-identification/spec.md).

## Development / Testing

Phase 1 runs entirely on a local Mac (Docker Compose: Mosquitto + Frigate + a throwaway Home
Assistant instance) — nothing touches production during this phase.

- **How to run it locally**: [`docs/testing/local-mac-testing.md`](docs/testing/local-mac-testing.md)
- **Current validation status**: [`specs/001-front-door-person-identification/validation-report.md`](specs/001-front-door-person-identification/validation-report.md)
- **Contribution rules** (including the Local Test Documentation Gate): [`CONTRIBUTING.md`](CONTRIBUTING.md)

> **T019 (the pre-development validation gate) must PASS before any feature implementation
> task (T020+) begins.** See the validation report above for current status.

## Production Architecture

The Raspberry Pi 3 is, and remains, the production Home Assistant control plane — it is
**not** the AI/Frigate compute host, which is a separate, not-yet-selected dedicated machine.

- **Full production design**: [`docs/production/production-deployment.md`](docs/production/production-deployment.md)

## Project documents

- [`specs/001-front-door-person-identification/spec.md`](specs/001-front-door-person-identification/spec.md) — feature specification
- [`specs/001-front-door-person-identification/plan.md`](specs/001-front-door-person-identification/plan.md) — implementation plan
- [`specs/001-front-door-person-identification/tasks.md`](specs/001-front-door-person-identification/tasks.md) — task breakdown, phase-gated by the constitution's Phase-Gated Delivery principle
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — authoritative project principles
