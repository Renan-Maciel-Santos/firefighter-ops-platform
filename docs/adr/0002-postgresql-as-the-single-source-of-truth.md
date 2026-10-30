# ADR 0002: PostgreSQL as the single source of truth

- **Status:** Accepted (recorded retroactively)
- **Deciders:** Renan Maciel

## Context

Before the platform, the battalion's data lived in three corporate systems without APIs (personnel, fleet status, incident reports), spreadsheets on a network share and a Google Sheet. Each morning, people consolidated it by hand, and different reports could disagree because they were built from different copies.

Sources also differ in freshness. Vehicle status, for example, comes both from the live fleet system and from a spreadsheet that is loaded less often, so a later spreadsheet load could overwrite a more recent status.

## Decision

1. **One database, one schema per staff section.** PostgreSQL holds every source in schemas that mirror the battalion's staff sections (`b1`, `b3`, `b4`, `b5`, `sjd`, `uge`), plus `app` for the dashboard and `bia` for the assistant. The dashboard, the assistant and the reports all read from it.
2. **Business logic in views.** Shared definitions (staff availability, force map, response times) are SQL views, so every consumer reads the same result.
3. **The database protects the freshest source.** The trigger `b4.fn_viaturas_trava_siopm` keeps a vehicle status that came from the live fleet system from being overwritten by the spreadsheet load for 3 days.
4. **Idempotent, audited loads.** Every ETL run is recorded in `b1.etl_status` (rows read, inserted, updated, errors). Snapshot loads are deduplicated by the SHA-256 of their content with `ON CONFLICT DO NOTHING`, so re-running a load with an unchanged file is harmless.

## Consequences

### Positive

- One answer to each question, whether it is asked in the dashboard, on WhatsApp or in a report.
- Data integrity rules that matter (source freshness) are enforced even if a loader is wrong.
- Every load can be traced and safely repeated.

### Negative / Trade-offs

- Logic in views and triggers is less visible to Python-only readers and needs SQL review.
- The schema is maintained as a `pg_dump --schema-only` snapshot plus the `migra_*.sql` history, not with a migration tool such as Alembic.

## References

- [`db/demo/schema.sql`](../../db/demo/schema.sql): schemas, views and the freshness trigger
- [`B3/mapa_operacional.py`](../../B3/mapa_operacional.py): content-hash deduplication
- [ADR 0005](0005-repository-organised-by-staff-section.md): why the code follows the same sections
