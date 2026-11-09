# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Finance section.** Monthly cost of each sub-command (SGB) from what the municipalities pay per station (phone, water, power, fuel, fleet maintenance, food, other), with a monthly entry form and the procurement unit's own funds by paying source. Replaces a shared Google Sheet.
- **Per-user permissions.** The admin picks the tabs each staff member sees on a new Permissions tab (`app.usuarios.abas_personalizadas`; NULL keeps the section default). The discipline tab stays restricted to officers and its own section.
- **Fleet indicators.** Real availability from the CAD snapshots, use vs. age, maintenance and fuel cost per vehicle, incomplete records and a status timeline per vehicle. The fleet tab is split into Indicators and Fleet list.
- **Divers in the assistant.** `/consulta/resumo-operacional` returns water and divers per station and the divers' names (dive course crossed with the current roster).


## [1.0.0] - 2026-11-04

First release: public, sanitized copy of the production data platform and WhatsApp assistant running for the 11º Grupamento de Bombeiros (CBPMESP), covering ~500 personnel, 25 fire stations and ~190 vehicles with 100% synthetic data.

### Added

- **The LLM never produces a number.** Dedicated `/consulta/*` endpoints format output verbatim in WhatsApp markup; the assistant relays text directly without numerical hallucination or calculation ([ADR 0001](docs/adr/0001-the-llm-never-produces-a-number.md)).
- **PostgreSQL as single source of truth.** Centralized schema consolidating personnel, incident history, fleet status, health inspections and procurement across ~40 database views ([ADR 0002](docs/adr/0002-postgresql-as-the-single-source-of-truth.md)).
- **One place per rule.** Unified access control and role-based permissions in `webapp/acesso.py`, and single-source staff classification in `webapp/efetivo_regras.py` shared between dashboard and assistant ([ADR 0003](docs/adr/0003-one-place-per-rule.md)).
- **Autonomous operations and watchdog.** `bia_watchdog.py` monitors API, Postgres, n8n and gateway health, auto-restarts stalled services, reports load freshness, and integrates a dead man's switch for host outage detection ([ADR 0004](docs/adr/0004-operating-without-an-operations-team.md)).
- **Database fleet protection trigger.** Trigger `b4.fn_viaturas_trava_siopm` protects live CAD/telemetry status from being overwritten by delayed spreadsheet imports for 3 days.
- **Audited and idempotent data loads.** `b1.etl_status` tracks row counts and execution state; snapshot loads are deduplicated via SHA-256 payload hashing with `ON CONFLICT DO NOTHING`.
- **Management dashboard.** 14 role-based tabs covering personnel tables, daily force maps, response times, fleet readiness, health restrictions, and staff reallocation simulation.
- **Evaluation harness.** Replays question sets in `avaliacao_llm/` benchmarking candidate prompts against hallucinated names, tool invocation errors, context limits, and multi-turn lookup queries.
- **Synthetic data generator.** `seed/gerar_dados_ficticios.py` generates consistent, anonymized records for demonstration with a mandatory safety guard (`test_seed_guard.py`) preventing execution against production instances.
- **Document and report generators.** Automated generation of operational service orders (`python-docx`) and management briefing presentations (`python-pptx`).
- **Architecture decision records.** ADRs 0001 through 0005 documenting core operational, data integrity and system design decisions.

### Security

- Production safety guard: database initialization strictly requires the `demo.instancia` marker before dropping schemas, preventing accidental execution against non-demo environments.
- Fail-fast environment configuration: missing mandatory secrets abort startup immediately with explicit diagnostics in `_env.py`.
- Automated encrypted backups: daily database dumps encrypted with AES-256-GCM via scrypt-derived keying (`backup_11gb.py`).
- Isolated ports: demo database binds to port `55432`, avoiding collisions and unintended exposures on the standard PostgreSQL port.

[Unreleased]: https://github.com/Renan-Maciel-Santos/firefighter-ops-platform/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Renan-Maciel-Santos/firefighter-ops-platform/releases/tag/v1.0.0
