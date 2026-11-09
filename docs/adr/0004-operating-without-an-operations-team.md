# ADR 0004: Operating without an operations team

- **Status:** Accepted (recorded retroactively)
- **Date of the decision:** not recorded
- **Deciders:** Renan Maciel

## Context

The platform runs on a single host inside the battalion and is maintained by one developer. There is no on-call team. The assistant depends on a chain of four services (WhatsApp gateway, n8n, the dashboard API and PostgreSQL), and the data depends on loads that run on a schedule.

The most dangerous failures are the silent ones. With the API down, the WhatsApp gateway stays connected, receives every message and answers every question with an error, with no visible symptom on the gateway itself. A load that stops running leaves the dashboard showing data that is quietly getting older. And a watchdog running on the same host cannot report that the host itself is off.

## Decision

1. **Check every link, not just the entry point.** [`bia_watchdog.py`](../../bia_watchdog.py) checks each service in the chain separately, and also the freshness of each data load.
2. **Recover automatically when it is safe.** It restarts stopped containers and the API on its own.
3. **Alert once per incident.** A notification is sent when an incident starts, not on every check, so alerts are not ignored.
4. **Detect a dead host from outside.** Each watchdog run pings an external dead man's switch (healthchecks.io), which alerts when the pings stop, covering a powered-off or disconnected host.
5. **Encrypted, off-host backups.** [`backup_11gb.py`](../../backup_11gb.py) produces daily dumps of the databases, secrets and the assistant's workflow, encrypted with AES-256-GCM using a key derived with scrypt, and copies them off the host. A `--verificar` mode checks existing backups.
6. **Secrets fail fast.** [`_env.py`](../../_env.py) refuses to start when a required secret is missing and names it, instead of failing later with a misleading error such as a wrong password.

## Consequences

### Positive

- Failures that users would not notice are detected and, in most cases, repaired before anyone asks.
- Losing the host does not mean losing the data.
- Misconfiguration is found at startup, with a clear message.

### Negative / Trade-offs

- The watchdog is itself a single process on the same host; the external dead man's switch covers it only for total failure, not for partial misbehaviour.
- Automatic restarts can hide a recurring problem; alerts per incident are kept so restarts remain visible.

## References

- [`bia_watchdog.py`](../../bia_watchdog.py)
- [`backup_11gb.py`](../../backup_11gb.py)
- [`_env.py`](../../_env.py)
