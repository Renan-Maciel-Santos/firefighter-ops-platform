# ADR 0003: One place per rule

- **Status:** Accepted (recorded retroactively)
- **Date of the decision:** 2026-09-09 (access control), 2026-09-11 (staff classification)
- **Deciders:** Renan Maciel

## Context

Two rules were duplicated across the code base:

- **Access control.** Each dashboard router carried its own list of allowed roles (`ALLOWED_PERFIS`), and the frontend carried another one in JavaScript (`PERFIL_ACCESS`). Adding a tab meant updating both; forgetting the backend left an endpoint answering anyone who knew its URL, even with the menu item hidden.
- **Staff classification.** Which unit a person belongs to, and whether they work on the front line or in administration, was computed by a copy of the same `CASE` expression in three places: the personnel card, the reallocation simulator and the assistant's staffing answer. When the rule changed (the fire safety section started to include additional teams), the three copies had to change together.

Two copies of the same decision drift apart silently.

## Decision

1. **Access control lives only in [`webapp/acesso.py`](../../webapp/acesso.py).** The backend enforces it on every route, and the frontend receives the allowed tabs from `/auth/me`. Hiding a menu item is a consequence of the rule, not the protection.
2. **Unknown roles see nothing.** Roles not defined in the module, including legacy ones from before the migration, are denied by default.
3. **Three roles.** `admin` (everything, plus user management), `officer` (every tab except user management) and `staff` (only the tabs of their own section).
4. **The assistant is the channel for front-line staff.** Personnel at the fire stations (421 of 501) have no dashboard login; they use the WhatsApp assistant, which only exposes curated, read-only answers.
5. **Staff classification lives only in [`webapp/efetivo_regras.py`](../../webapp/efetivo_regras.py)**, as SQL fragments shared by the dashboard and the assistant, so the card, the simulator and the WhatsApp answer cannot disagree.

## Consequences

### Positive

- A new tab or rule change is made once, and every consumer follows.
- Access errors fail closed: a missing entry denies instead of exposing data.
- Unit tests cover the rules directly ([`tests/unit/test_acesso.py`](../../tests/unit/test_acesso.py)).

### Negative / Trade-offs

- The shared SQL fragments are interpolated into queries. This is safe only because they are fixed constants in code, never user input, and the module documents that constraint.
- Some database views still carry their own version of the classification; the module documents where the shared rule does not apply.

## References

- [`webapp/acesso.py`](../../webapp/acesso.py)
- [`webapp/efetivo_regras.py`](../../webapp/efetivo_regras.py)
