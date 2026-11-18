# OpsLedger Operator Runbook

This runbook is for operators who start, stop, back up, upgrade, and
reconcile a single OpsLedger instance. OpsLedger is a modular monolith
backed by a single-instance SQLite database: there is no network
database server, and the HTTP adapter below is the lab-only
`http.server`-based adapter, not a production web server. The real
commands live in the application CLI `python -m opsledger.cli` — not in
the bootstrap module `python -m opsledger`, which keeps only stubs
(`migrate`, `serve`, `seed`, etc. exit 2 with "not implemented in
bootstrap") and a working `diagnostics` JSON.

## Start: migrate, then serve

Apply migrations first; the command applies pending migrations, prints
each applied id, exits 0 on success:

```
python -m opsledger.cli migrate DATABASE
```

On a fresh database this prints all 24 migration ids, one per line,
e.g. `0001_initial`, `0002_identity`, ... `0024_assets_listing_idx`.
On a second run against an already-migrated database there is no
output (all applied, nothing printed, exit 0). If applied migration
content changed on disk, the command fails with a checksum-mismatch
ConflictError (see Troubleshooting).

Start the server with defaults `127.0.0.1:8080`:

```
python -m opsledger.cli serve DATABASE
```

`serve` runs the pending migrations first (same rules), then serves.
Verify liveness with the health endpoint:

```
curl http://127.0.0.1:8080/api/v1/healthz
```

Expected response:

```
{"status": "ok"}
```

Optional flags: `--host H` and `--port P` change the bind address;
`--migrations DIR` points at a different directory of numbered SQL
migrations (default `opsledger/migrations`).

## Stop: bounded drain, then clean exit

Stop the server with SIGINT (Ctrl-C) or SIGTERM. `RouterServer.drain(
timeout)` waits (bounded, 5s default in the CLI) for in-flight requests
to finish, then `server_close()` runs and the process exits 0, so a
normal stop never abandons an active request; a handler exceeding the
timeout is abandoned by the bounded close rather than hanging the
process:

```
kill -TERM <pid>
```

## Seeding: demo profiles

Seed in Python with `opsledger.core.seeding.seed_profile(conn,
profile=..., seed=..., batch_size=...)`. Profiles shipped (rows per
concept):

- `tiny` — 2 orgs, 4 sites, 20 assets, 40 work orders, 100 movements.
- `medium` — 3 orgs, 15 sites, 5000 assets, 25000 work orders, 100000
  movements.
- `large` — 5 orgs, 50 sites, 25000 assets, 100000 work orders, 500000
  movements.

Use a fixed seed (default 20261118) for reproducibility. Re-runs are
restartable: rows are written with INSERT OR IGNORE, so an interrupted
run restarted converges to the same final state.
`build_manifest(conn, profile=..., seed=..., batch_size=...)` returns
the per-concept counts plus a logical checksum of the seeded state.
`large` stays outside the fast gate: run it only in dedicated
long-running jobs, never as part of quick validation.

## Backup and restore

Back up with `opsledger.core.backup.backup_database(source_conn,
target_path)`. The contract: the source must have no open transaction;
if it does, backup is refused (ValidationError, "commit or roll back
before backup") and the target file is never touched on refusal. An
existing file at the target path is overwritten by SQLite backup
semantics; that is intended.

Restore with `opsledger.core.backup.restore_database(backup_path,
target_path)`: it copies the backup and reopens it with the standard
profile.

## Upgrades from prior versions

Build a database as a prior milestone would have left it with
`opsledger.core.upgrade_fixtures.build_prior_database(target_path,
boundary=...)`. Milestone boundaries: m5 `0017_stock_ledger`,
m6 `0019_idempotency`, m7 `0022_maintenance`.

Then apply the remaining migrations with
`opsledger.core.upgrade_fixtures.upgrade_database(conn)`. After the
upgrade, check the state with
`opsledger.core.upgrade_fixtures.restore_diagnostics(conn)`; it reports
`integrity`, `foreign_key_violations`, `applied_migration_count`, and
per-table `counts`. Healthy values: `integrity` `ok`,
`foreign_key_violations` `0`, `applied_migration_count` `24`.

## Reconciliation

Verify one part/location balance against the recomputed stock movement
sum. It prints balance vs movement-sum JSON and exits 1 on mismatch:

```
python -m opsledger.reconcile_cli DATABASE --part PART_ID --location LOCATION_ID
```

Exit 0 means the persisted balance and the movement sum agree; exit 1
means they disagree (application errors print the public message to
stderr and also exit 1).

## Troubleshooting

- Checksum-mismatch ConflictError: content of an applied migration file
  changed on disk. Never edit applied migrations; restore the shipped
  file, then run migrate again.
- Backup refuses with "commit or roll back before backup": the source
  connection had an open transaction. Commit or roll back, then retry.
- Drain timeout on shutdown: in-flight requests still running after the
  bounded wait (5s default) are abandoned by the bounded close instead
  of hanging the process.
- Logs: structured redacted JSON logs, one object per line, correlated
  by request id. Send request ids with any report for traceability.

## Limitations

- Single-instance SQLite: no network database.
- The HTTP adapter is lab-only, built on Python's `http.server` module,
  and is not a production web server.
- No runtime network access.
- Python 3.12 and Node 22 baseline only.
- No pip or npm installation.
