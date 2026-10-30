# ADR 0005: Repository organised by staff section

- **Status:** Accepted (recorded retroactively)
- **Deciders:** Renan Maciel

## Context

The battalion is organised in staff sections, each responsible for its own data and processes:

| Section | Responsibility | Data loaded |
|---|---|---|
| **B/1** | Personnel | Staff, leaves, health inspections and restrictions, physical fitness tests |
| **B/3** | Operations | Daily force map, incidents, station coordinates |
| **B/4** | Logistics | Fleet and vehicle status |
| **B/5** | Public relations | Commendations |
| **SJD** | Justice and discipline | Disciplinary proceedings and monthly indicators |
| **UGE** | Budget execution unit | Procurement processes |

The people who maintain and use the data speak in these terms: a request comes from "the B/4", not from "the fleet module". Each section has its own spreadsheets, its own owners and its own pace of change.

## Decision

1. **One folder and one database schema per section** (`B1/` and `b1`, `B3/` and `b3`, and so on). Each folder holds the ETLs and SQL migrations for that section's data.
2. **Cross-cutting code lives outside the sections**: the dashboard and API in `webapp/`, shared ETL helpers in `_comum.py`, configuration in `_env.py`, logging in `_log.py`, and the load orchestrator in `rodar_etl_arquivos.py`.
3. **Domain language in Portuguese.** Comments and most identifiers use the vocabulary of the people who maintain the system; the public README and these ADRs are in English for outside readers.

## Consequences

### Positive

- A change requested by a section is found in one place, named the way the section names it.
- Sections evolve independently; a new spreadsheet for B/5 does not touch B/1.
- The structure matches the organisation's own boundaries, in the spirit of bounded contexts in Domain-Driven Design.

### Negative / Trade-offs

- Readers outside the organisation need this ADR, or the README, to understand the folder names.
- Technical layers (collectors, loaders, migrations) are repeated in each section instead of grouped together.

## References

- [ADR 0002](0002-postgresql-as-the-single-source-of-truth.md): one schema per section in the database
- [`rodar_etl_arquivos.py`](../../rodar_etl_arquivos.py): orchestration of the file-based loads
