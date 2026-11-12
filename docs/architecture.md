# Architecture

OpsLedger is a modular monolith: one Python package, one SQLite database, one
HTTP adapter. No framework in the baseline profile — no FastAPI, Django,
Flask, or ORM; standard-library Python 3.12 only.

## Layers

1. HTTP adapter (thin: routing, bounded JSON, error mapping)
2. Authentication and authorization
3. Domain services (business transactions, explicit identity context)
4. SQLite transactions / audit + transactional outbox

Dependencies point one way: services never import the HTTP adapter, and
handlers never contain business rules.

## Flow

```mermaid
flowchart TD
  UI["Browser UI"] --> API["HTTP adapter"]
  CLI["Application CLI"] --> SVC["Domain services"]
  API --> AUTH["Authentication and authorization"]
  AUTH --> SVC
  SVC --> DB["SQLite transactions"]
  SVC --> OUT["Audit and outbox"]
  OUT --> DB
  TEST["Independent acceptance runner"] --> API
```

## Layout

| Path | Responsibility |
| --- | --- |
| `opsledger/core/` | Errors, identity context, clock, IDs, database connections, migration runner |
| `opsledger/identity/` | Users, sessions, role checks, organization/site membership |
| `opsledger/assets/` | Sites, equipment, maintenance plans |
| `opsledger/workorders/` | State transitions, assignments, labor, checklists, comments |
| `opsledger/inventory/` | Parts, balances, reservations, movements, reconciliation |
| `opsledger/purchasing/` | Requests, approvals, purchase orders, receipts |
| `opsledger/incidents/` | Incidents, corrective actions, relationships to repairs |
| `opsledger/reporting/` | Authorized search, dashboards, CSV exports |
| `opsledger/audit/` | Append-only application audit and transactional outbox |
| `opsledger/http/` | Routing, bounded JSON, error mapping, cookie/CSRF handling, static allowlist |
| `opsledger/migrations/` | Append-only numbered SQL migrations with recorded checksums |
| `web/` | HTML, CSS, ES modules, no generated bundles |

All module directories are orientation for later tasks; the bootstrap ships
only `opsledger/__init__.py` and `opsledger/__main__.py`.

## Core foundation (T001)

### Error types (`opsledger/core/errors.py`)

All application errors derive from `ApplicationError(Exception)`:

- `ApplicationError(message, *, code=None, fields=None)` — base class with
  `code` (stable machine-readable string, default `"application_error"`),
  public `message` (via `str(error)`), and optional safe `fields` dict
  (field name -> public reason). `to_payload()` returns the public JSON
  envelope: `{"code", "message"}` plus `"fields"` when present.
- `ValidationError` — default code `validation_error`; caller input failed
  validation.
- `NotFoundError` — default code `not_found`; record missing in scope.
- `PermissionDeniedError` — default code `permission_denied`; caller lacks
  membership or role.
- `ConflictError` — default code `conflict`; request conflicts with current
  state.

Messages never contain tracebacks or internal details. Subclass codes may
be overridden per raise site (`NotFoundError("x", code="work_order_not_found")`).

### UTC clocks (`opsledger/core/clock.py`)

- `Clock` — protocol: `now() -> datetime` (timezone-aware UTC) and
  `timestamp() -> str` (second-precision RFC3339 ending in `Z`).
- `RealClock` — wall clock; always reports timezone-aware UTC.
- `FixedClock(instant)` — deterministic test clock; the instant is
  normalized to UTC and truncated to second precision, so repeated reads
  are identical.
- `format_rfc3339(value)` — serializes an aware datetime as
  `2026-01-01T00:00:00Z` (UTC, `Z` suffix, second precision).
- `require_aware_utc(value)` — returns `value` converted to UTC; rejects
  naive datetimes with `ValidationError` (`validation_error`).

Later business services take a `Clock` (injected; `FixedClock` in tests)
and serialize all stored timestamps through `format_rfc3339`.

## Persistence foundation (T002)

### SQLite connections (`opsledger/core/db.py`)

- `connect(path)` — opens a SQLite connection (a `sqlite3.Connection`
  subclass) to `path` with the OpsLedger profile: `foreign_keys=ON`,
  `journal_mode=WAL`, `synchronous=NORMAL`, and
  `row_factory=sqlite3.Row`. Connections are never shared across threads:
  use each connection on its creating thread only (`check_same_thread=True`
  is kept, so SQLite enforces this).
- `transaction(conn)` — context manager that runs a block inside one
  `BEGIN IMMEDIATE` transaction. On clean exit the transaction is
  committed; on any exception it is rolled back and the original error is
  re-raised. Nested use raises `ConflictError` with stable code
  `"conflict"` and a public message.

Usage:

```python
from opsledger.core.db import connect, transaction

conn = connect(path)
with transaction(conn) as tx:
    tx.execute("INSERT ...")
```

sqlite3 database errors (`IntegrityError`, `OperationalError`) propagate
unchanged from `transaction()` blocks: they are never swallowed and never
wrapped into application errors. All SQL is parameterized.

## Schema foundation (T003)

### Migration runner (`opsledger/core/migrations.py`)

Public interface — one function:

- `migrate(conn, directory, *, clock=None) -> list[str]` — applies pending
  SQL migrations from `directory` to the SQLite connection `conn` and
  returns the list of `migration_id` values applied in this call, in
  application order. Pass `clock` to make `applied_at` deterministic in
  tests; the real wall clock is used by default.

Runner behavior:

- Creates the `schema_migrations` history table when absent:
  `id` INTEGER PRIMARY KEY, `migration_id` TEXT NOT NULL UNIQUE,
  `checksum` TEXT NOT NULL, `applied_at` TEXT NOT NULL.
- Lists `*.sql` files in `directory` and sorts them by their numeric prefix
  (`NNN_name.sql`); a file without a numeric prefix raises
  `ValidationError` with the stable subclass code `validation_error`.
- Refuses changed applied files: loads the recorded history first, and if
  any already-applied migration's file content changed, raises
  `ConflictError` naming the `migration_id` before running anything —
  nothing is applied when any checksum mismatch exists (check all first,
  then apply).
- Applies each not-yet-applied migration inside one `transaction(conn)`
  block and records `(migration_id, checksum, applied_at)` in the same
  transaction, so schema statements and their history row commit or roll
  back together. `migration_id` is the filename without the `.sql` suffix;
  `checksum` is the sha256 hex digest of the exact file bytes.
- Skips already-applied migrations whose recorded checksum still matches
  the file's current checksum, so a second run is a no-op.

Conventions:

- Migration filenames are append-only numbered SQL files: `NNN_name.sql`.
  `applied_at` is RFC3339 UTC ending in `Z` with second precision.
- The history row for an applied migration is append-only: an applied
  migration's file must never change (SHA-256 makes tampering evident).
- Missing numbers are not errors and may not be backfilled by editing:
  `001` can be applied while `002` is absent; `002` applies when it
  reappears.
- `opsledger/migrations/` currently ships one runner fixture,
  `0001_initial.sql` (creates the `schema_notes` table); it is not a
  business table.

Usage:

```python
from opsledger.core.migrations import migrate

migrate(conn, "opsledger/migrations")
```
